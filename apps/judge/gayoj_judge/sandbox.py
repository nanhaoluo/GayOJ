from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from .languages import get_language_spec
from .runner import CodeJudgeTask, CodeTestCase, CompileOutcome, RunOutcome


DEFAULT_RUNNER_IMAGE = os.getenv("GAYOJ_JUDGE_RUNNER_IMAGE", "gayoj/judge-runner:ubuntu24.04")
CONTAINER_WORKDIR = "/work"


@dataclass(frozen=True)
class SandboxLimits:
    time_limit_ms: int = 1000
    memory_limit_mb: int = 128
    compile_timeout_ms: int = 10_000
    pids_limit: int = 64
    cpu_count: float = 1.0
    tmpfs_size_mb: int = 64
    output_limit_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if self.time_limit_ms <= 0:
            raise ValueError("time_limit_ms must be positive")
        if self.memory_limit_mb <= 0:
            raise ValueError("memory_limit_mb must be positive")
        if self.compile_timeout_ms <= 0:
            raise ValueError("compile_timeout_ms must be positive")
        if self.pids_limit <= 0:
            raise ValueError("pids_limit must be positive")
        if self.cpu_count <= 0:
            raise ValueError("cpu_count must be positive")
        if self.tmpfs_size_mb <= 0:
            raise ValueError("tmpfs_size_mb must be positive")
        if self.output_limit_bytes <= 0:
            raise ValueError("output_limit_bytes must be positive")


@dataclass(frozen=True)
class SandboxResult:
    verdict: str
    stage: str
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    message: str = ""
    command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DockerArtifact:
    work_dir: Path
    language: str


Runner = Callable[..., subprocess.CompletedProcess[str]]


class DockerSandboxExecutor:
    """Run user code only inside a constrained Docker container."""

    def __init__(
        self,
        *,
        image: str = DEFAULT_RUNNER_IMAGE,
        docker_bin: str = "docker",
        runner: Runner = subprocess.run,
        work_root: Path | None = None,
    ) -> None:
        self.image = image
        self.docker_bin = docker_bin
        self.runner = runner
        self.work_root = work_root

    def compile(self, task: CodeJudgeTask) -> CompileOutcome:
        started = time.perf_counter()
        try:
            spec = get_language_spec(task.language)
        except ValueError as exc:
            return CompileOutcome(ok=False, message=str(exc), time_ms=_elapsed_ms(started))

        work_dir = Path(tempfile.mkdtemp(prefix="gayoj-sandbox-", dir=self.work_root)).resolve()
        try:
            os.chmod(work_dir, 0o777)
        except OSError:
            pass
        (work_dir / spec.source_file).write_text(task.source_code, encoding="utf-8", newline="\n")
        artifact = DockerArtifact(work_dir=work_dir, language=task.language)

        if not spec.compile_command:
            return CompileOutcome(ok=True, artifact=artifact, time_ms=_elapsed_ms(started))

        result = self._run_container(
            stage="compile",
            work_dir=work_dir,
            inner_command=spec.compile_command,
            stdin="",
            timeout_ms=SandboxLimits().compile_timeout_ms,
            limits=SandboxLimits(time_limit_ms=task.time_limit_ms, memory_limit_mb=task.memory_limit_mb),
        )
        if result.exit_code != 0:
            self.cleanup(artifact)
            return CompileOutcome(
                ok=False,
                artifact=None,
                message=result.stderr or result.message,
                time_ms=_elapsed_ms(started),
            )
        return CompileOutcome(ok=True, artifact=artifact, message=result.stderr, time_ms=_elapsed_ms(started))

    def run(self, task: CodeJudgeTask, artifact: object, test_case: CodeTestCase) -> RunOutcome:
        if not isinstance(artifact, DockerArtifact):
            return RunOutcome(status="system_error", message="Invalid Docker sandbox artifact")

        try:
            spec = get_language_spec(artifact.language)
        except ValueError as exc:
            return RunOutcome(status="system_error", message=str(exc))

        limits = SandboxLimits(
            time_limit_ms=test_case.time_limit_ms or task.time_limit_ms,
            memory_limit_mb=test_case.memory_limit_mb or task.memory_limit_mb,
            output_limit_bytes=test_case.output_limit_bytes or SandboxLimits().output_limit_bytes,
        )
        result = self._run_container(
            stage="run",
            work_dir=artifact.work_dir,
            inner_command=spec.run_command,
            stdin=test_case.input,
            timeout_ms=limits.time_limit_ms,
            limits=limits,
        )
        status = _run_status_from_verdict(result.verdict)
        message = result.message
        stdout = result.stdout
        if len(stdout.encode("utf-8")) > limits.output_limit_bytes:
            status = "output_limit_exceeded"
            message = "Program exceeded the configured output limit."
            stdout = stdout[: limits.output_limit_bytes]
        return RunOutcome(
            status=status,
            stdout=stdout,
            stderr=result.stderr,
            message=message,
            exit_code=result.exit_code,
            time_ms=result.duration_ms,
        )

    def cleanup(self, artifact: object) -> None:
        if isinstance(artifact, DockerArtifact):
            shutil.rmtree(artifact.work_dir, ignore_errors=True)

    def preview_commands(
        self,
        *,
        language: str,
        limits: SandboxLimits | None = None,
        work_dir: Path | str = "<workdir>",
    ) -> dict[str, list[str] | None]:
        spec = get_language_spec(language)
        active_limits = limits or SandboxLimits()
        compile_command = (
            self.build_docker_command(
                work_dir=work_dir,
                inner_command=spec.compile_command,
                timeout_ms=active_limits.compile_timeout_ms,
                limits=active_limits,
            )
            if spec.compile_command
            else None
        )
        run_command = self.build_docker_command(
            work_dir=work_dir,
            inner_command=spec.run_command,
            timeout_ms=active_limits.time_limit_ms,
            limits=active_limits,
        )
        return {"compile_command": compile_command, "run_command": run_command}

    def execute(
        self,
        *,
        language: str,
        source_code: str,
        stdin: str = "",
        limits: SandboxLimits | None = None,
    ) -> SandboxResult:
        active_limits = limits or SandboxLimits()
        try:
            spec = get_language_spec(language)
        except ValueError as exc:
            return SandboxResult(verdict="unsupported_language", stage="prepare", message=str(exc))

        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="gayoj-sandbox-", dir=self.work_root) as raw_work_dir:
            work_dir = Path(raw_work_dir).resolve()
            try:
                os.chmod(work_dir, 0o777)
            except OSError:
                pass
            source_path = work_dir / spec.source_file
            source_path.write_text(source_code, encoding="utf-8", newline="\n")

            if spec.compile_command:
                compile_result = self._run_container(
                    stage="compile",
                    work_dir=work_dir,
                    inner_command=spec.compile_command,
                    stdin="",
                    timeout_ms=active_limits.compile_timeout_ms,
                    limits=active_limits,
                )
                if compile_result.exit_code != 0:
                    return compile_result

            run_result = self._run_container(
                stage="run",
                work_dir=work_dir,
                inner_command=spec.run_command,
                stdin=stdin,
                timeout_ms=active_limits.time_limit_ms,
                limits=active_limits,
            )
            if len(run_result.stdout.encode("utf-8")) > active_limits.output_limit_bytes:
                return SandboxResult(
                    verdict="output_limit_exceeded",
                    stage="run",
                    stdout=run_result.stdout[: active_limits.output_limit_bytes],
                    stderr=run_result.stderr,
                    exit_code=run_result.exit_code,
                    duration_ms=_elapsed_ms(started),
                    message="Sandbox output exceeded the configured limit.",
                    command=run_result.command,
                )
            return SandboxResult(
                verdict=run_result.verdict,
                stage=run_result.stage,
                stdout=run_result.stdout,
                stderr=run_result.stderr,
                exit_code=run_result.exit_code,
                duration_ms=_elapsed_ms(started),
                message=run_result.message,
                command=run_result.command,
            )

    def build_docker_command(
        self,
        *,
        work_dir: Path | str,
        inner_command: Sequence[str],
        timeout_ms: int,
        limits: SandboxLimits,
    ) -> list[str]:
        timeout_seconds = max(1, (timeout_ms + 999) // 1000)
        memory = f"{limits.memory_limit_mb}m"
        mount_source = str(work_dir)
        return [
            self.docker_bin,
            "run",
            "--rm",
            "--network",
            "none",
            "--memory",
            memory,
            "--memory-swap",
            memory,
            "--cpus",
            _format_cpu(limits.cpu_count),
            "--pids-limit",
            str(limits.pids_limit),
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--user",
            "65534:65534",
            "--workdir",
            CONTAINER_WORKDIR,
            "--mount",
            f"type=bind,source={mount_source},target={CONTAINER_WORKDIR}",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={limits.tmpfs_size_mb}m",
            self.image,
            "timeout",
            "--signal=KILL",
            f"{timeout_seconds}s",
            *inner_command,
        ]

    def _run_container(
        self,
        *,
        stage: str,
        work_dir: Path,
        inner_command: Sequence[str],
        stdin: str,
        timeout_ms: int,
        limits: SandboxLimits,
    ) -> SandboxResult:
        command = self.build_docker_command(
            work_dir=work_dir,
            inner_command=inner_command,
            timeout_ms=timeout_ms,
            limits=limits,
        )
        host_timeout = max(1.0, timeout_ms / 1000 + 3.0)
        started = time.perf_counter()
        try:
            completed = self.runner(
                command,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=host_timeout,
                shell=False,
            )
        except FileNotFoundError:
            return SandboxResult(
                verdict="sandbox_error",
                stage=stage,
                exit_code=None,
                duration_ms=_elapsed_ms(started),
                message=f"Docker executable not found: {self.docker_bin}",
                command=command,
            )
        except subprocess.TimeoutExpired as exc:
            return SandboxResult(
                verdict="time_limit_exceeded" if stage == "run" else "compile_error",
                stage=stage,
                stdout=_decode_timeout_payload(exc.stdout),
                stderr=_decode_timeout_payload(exc.stderr),
                exit_code=None,
                duration_ms=_elapsed_ms(started),
                message="Sandbox process exceeded host-side timeout.",
                command=command,
            )

        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        verdict = _verdict_from_exit(stage, completed.returncode, stderr)
        return SandboxResult(
            verdict=verdict,
            stage=stage,
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            duration_ms=_elapsed_ms(started),
            message=_message_from_verdict(verdict),
            command=command,
        )


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _format_cpu(cpu_count: float) -> str:
    value = f"{cpu_count:.2f}".rstrip("0").rstrip(".")
    return value or "1"


def _decode_timeout_payload(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _verdict_from_exit(stage: str, return_code: int, stderr: str) -> str:
    if return_code == 0:
        return "ok"
    if stage == "compile":
        return "compile_error"
    if return_code in {124, 137}:
        return "time_limit_exceeded"
    lowered = stderr.lower()
    if "out of memory" in lowered or "oom" in lowered:
        return "memory_limit_exceeded"
    return "runtime_error"


def _message_from_verdict(verdict: str) -> str:
    return {
        "ok": "Sandbox command completed.",
        "compile_error": "Compilation failed inside the sandbox.",
        "runtime_error": "Program exited with a non-zero status inside the sandbox.",
        "time_limit_exceeded": "Program exceeded the configured time limit.",
        "memory_limit_exceeded": "Program exceeded the configured memory limit.",
        "output_limit_exceeded": "Program exceeded the configured output limit.",
    }.get(verdict, "Sandbox command failed.")


def _run_status_from_verdict(verdict: str) -> str:
    return {
        "ok": "accepted",
        "runtime_error": "runtime_error",
        "time_limit_exceeded": "time_limit_exceeded",
        "memory_limit_exceeded": "memory_limit_exceeded",
        "output_limit_exceeded": "output_limit_exceeded",
        "sandbox_error": "system_error",
    }.get(verdict, "system_error")
