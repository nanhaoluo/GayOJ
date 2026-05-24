from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
JUDGE_ROOT = ROOT / "apps" / "judge"

if str(JUDGE_ROOT) not in sys.path:
    sys.path.insert(0, str(JUDGE_ROOT))

from gayoj_judge import CodeJudgeTask, CodeTestCase, DockerSandboxExecutor, SandboxLimits, get_language_spec  # noqa: E402


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append({"command": command, "kwargs": kwargs})
        return subprocess.CompletedProcess(command, 0, stdout="3\n", stderr="")


def command_text(command: list[str]) -> str:
    return " ".join(command)


def test_docker_sandbox_dry_run_contains_required_isolation_flags() -> None:
    executor = DockerSandboxExecutor(image="gayoj/judge-runner:test")
    commands = executor.preview_commands(
        language="python",
        limits=SandboxLimits(time_limit_ms=750, memory_limit_mb=64),
    )
    run_command = commands["run_command"]

    assert run_command is not None
    text = command_text(run_command)
    assert "--network none" in text
    assert "--memory 64m" in text
    assert "--memory-swap 64m" in text
    assert "--cpus 1" in text
    assert "--pids-limit 64" in text
    assert "--read-only" in text
    assert "--cap-drop ALL" in text
    assert "--security-opt no-new-privileges" in text
    assert "--user 65534:65534" in text
    assert "--tmpfs /tmp:rw,noexec,nosuid,size=64m" in text
    assert "timeout --signal=KILL 1s" in text
    assert "gayoj/judge-runner:test" in run_command


def test_docker_sandbox_invokes_docker_without_shell_and_cleans_tempdir() -> None:
    runner = FakeRunner()
    executor = DockerSandboxExecutor(image="gayoj/judge-runner:test", runner=runner)
    result = executor.execute(
        language="python",
        source_code="import sys\nprint(sum(map(int, sys.stdin.read().split())))\n",
        stdin="1 2\n",
        limits=SandboxLimits(time_limit_ms=1000, memory_limit_mb=128),
    )

    assert result.verdict == "ok"
    assert [call["kwargs"]["shell"] for call in runner.calls] == [False, False]

    run_command = runner.calls[-1]["command"]
    assert isinstance(run_command, list)
    mount_arg = run_command[run_command.index("--mount") + 1]
    assert isinstance(mount_arg, str)
    source_part = mount_arg.split(",")[1]
    workdir = Path(source_part.removeprefix("source="))
    assert not workdir.exists()


def test_docker_sandbox_maps_compile_failure_to_compile_error() -> None:
    def fail_compile(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="syntax error")

    executor = DockerSandboxExecutor(image="gayoj/judge-runner:test", runner=fail_compile)
    result = executor.execute(
        language="cpp",
        source_code="int main() {",
        limits=SandboxLimits(time_limit_ms=1000, memory_limit_mb=128),
    )

    assert result.verdict == "compile_error"
    assert result.stage == "compile"
    assert "syntax error" in result.stderr


def test_docker_sandbox_rejects_unsupported_language_before_running() -> None:
    runner = FakeRunner()
    executor = DockerSandboxExecutor(image="gayoj/judge-runner:test", runner=runner)
    result = executor.execute(language="rust", source_code="fn main() {}")

    assert result.verdict == "unsupported_language"
    assert runner.calls == []


def test_docker_sandbox_implements_worker_executor_contract() -> None:
    runner = FakeRunner()
    executor = DockerSandboxExecutor(image="gayoj/judge-runner:test", runner=runner)
    task = CodeJudgeTask(
        submission_id="S1",
        problem_id="P1001",
        language="python",
        source_code="print(input())\n",
        time_limit_ms=500,
        memory_limit_mb=64,
        test_cases=[CodeTestCase(id="sample-1", input="3\n", expected_output="3\n")],
    )

    compile_result = executor.compile(task)
    assert compile_result.ok
    assert compile_result.artifact is not None
    run_result = executor.run(task, compile_result.artifact, task.test_cases[0])
    executor.cleanup(compile_result.artifact)

    assert run_result.status == "accepted"
    assert run_result.stdout == "3\n"
    run_command = runner.calls[-1]["command"]
    assert isinstance(run_command, list)
    assert "--network" in run_command
    assert "none" in run_command


def test_language_specs_follow_p0_worker_contract() -> None:
    cpp = get_language_spec("cpp")
    python = get_language_spec("python")

    assert cpp.source_file == "Main.cpp"
    assert cpp.compile_command is not None
    assert "-DONLINE_JUDGE" in cpp.compile_command
    assert "-static" in cpp.compile_command
    assert python.compile_command == ("python3", "-m", "py_compile", "Main.py")
