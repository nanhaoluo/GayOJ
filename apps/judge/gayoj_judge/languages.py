from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageSpec:
    source_file: str
    compile_command: tuple[str, ...] | None
    run_command: tuple[str, ...]


LANGUAGE_SPECS: dict[str, LanguageSpec] = {
    "c": LanguageSpec(
        source_file="Main.c",
        compile_command=(
            "gcc",
            "-std=c17",
            "-O2",
            "-Wall",
            "-Wextra",
            "-DONLINE_JUDGE",
            "-static",
            "-Wl,--no-relax",
            "-Wl,--no-pie",
            "-mcmodel=medium",
            "-o",
            "Main",
            "Main.c",
        ),
        run_command=("./Main",),
    ),
    "cpp": LanguageSpec(
        source_file="Main.cpp",
        compile_command=(
            "g++",
            "-std=c++17",
            "-O2",
            "-Wall",
            "-Wextra",
            "-DONLINE_JUDGE",
            "-static",
            "-Wl,--no-relax",
            "-Wl,--no-pie",
            "-mcmodel=medium",
            "-o",
            "Main",
            "Main.cpp",
        ),
        run_command=("./Main",),
    ),
    "java": LanguageSpec(
        source_file="Main.java",
        compile_command=("javac", "-J-Xms1024M", "-J-Xmx1024M", "-J-Xss64M", "-encoding", "UTF-8", "Main.java"),
        run_command=("java", "-Dfile.encoding=UTF-8", "-XX:+UseSerialGC", "-Xss64M", "-cp", ".", "Main"),
    ),
    "python": LanguageSpec(
        source_file="Main.py",
        compile_command=("python3", "-m", "py_compile", "Main.py"),
        run_command=("python3", "Main.py"),
    ),
}


def get_language_spec(language: str) -> LanguageSpec:
    key = language.strip().lower()
    if key not in LANGUAGE_SPECS:
        supported = ", ".join(sorted(LANGUAGE_SPECS))
        raise ValueError(f"Unsupported judge language: {language}. Supported languages: {supported}")
    return LANGUAGE_SPECS[key]
