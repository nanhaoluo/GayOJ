from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .models import Problem, ProblemCreate, ProblemPackageFormat, ProblemType


class ProblemPackageError(ValueError):
    pass


@dataclass(frozen=True)
class ImportedProblem:
    index: int
    source_id: str | None
    payload: ProblemCreate


_DIFFICULTIES = {"入门", "基础", "提高", "困难"}


def export_problem_package(
    format: ProblemPackageFormat,
    problems: list[tuple[Problem, dict[str, Any]]],
) -> tuple[str, str]:
    if format == "fps":
        return _export_fps(problems), "application/xml"
    if format == "qdu":
        return json.dumps(_export_qdu(problems), ensure_ascii=False, indent=2), "application/json"
    if format == "hydro":
        return json.dumps(_export_hydro(problems), ensure_ascii=False, indent=2), "application/json"
    raise ProblemPackageError(f"Unsupported problem package format: {format}")


def parse_problem_package(format: ProblemPackageFormat, content: str) -> list[ImportedProblem]:
    try:
        if format == "fps":
            raw_items = _read_fps(content)
        elif format == "qdu":
            raw_items = _read_qdu(content)
        elif format == "hydro":
            raw_items = _read_hydro(content)
        else:
            raise ProblemPackageError(f"Unsupported problem package format: {format}")
    except (json.JSONDecodeError, ET.ParseError) as exc:
        raise ProblemPackageError(f"Invalid {format} package: {exc}") from exc

    imported: list[ImportedProblem] = []
    for index, raw in enumerate(raw_items):
        source_id = _text(raw.get("id") or raw.get("source_id")) or None
        try:
            payload = ProblemCreate(**_normalize_problem_payload(raw))
        except (TypeError, ValueError, ValidationError) as exc:
            raise ProblemPackageError(f"Problem #{index + 1} is invalid: {exc}") from exc
        imported.append(ImportedProblem(index=index, source_id=source_id, payload=payload))
    return imported


def package_filename(format: ProblemPackageFormat) -> str:
    extension = "xml" if format == "fps" else "json"
    return f"gayoj-problems.{format}.{extension}"


def _problem_payload(problem: Problem, judge_config: dict[str, Any]) -> dict[str, Any]:
    payload = problem.model_dump(mode="json")
    payload["judge_config"] = judge_config
    return payload


def _export_qdu(problems: list[tuple[Problem, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "format": "qdu",
        "version": "1.0",
        "generator": "gayoj",
        "problems": [
            {
                "_id": problem.id,
                "title": problem.title,
                "problem_type": problem.type,
                "difficulty": problem.difficulty,
                "tags": problem.tags,
                "description": problem.statement,
                "input_description": problem.input_format,
                "output_description": problem.output_format,
                "samples": problem.samples,
                "options": problem.options,
                "blanks": problem.blanks,
                "time_limit": problem.time_limit_ms,
                "memory_limit": problem.memory_limit_mb,
                "visible": problem.visible,
                "offline_enabled": problem.offline_enabled,
                "offline_policy": problem.offline_policy.model_dump(mode="json"),
                "judge_config": judge_config,
            }
            for problem, judge_config in problems
        ],
    }


def _export_hydro(problems: list[tuple[Problem, dict[str, Any]]]) -> dict[str, Any]:
    return {
        "format": "hydro",
        "version": "1.0",
        "generator": "gayoj",
        "problems": [
            {
                "pid": problem.id,
                "title": problem.title,
                "type": problem.type,
                "difficulty": problem.difficulty,
                "tags": problem.tags,
                "content": problem.statement,
                "input": problem.input_format,
                "output": problem.output_format,
                "samples": problem.samples,
                "options": problem.options,
                "blanks": problem.blanks,
                "limits": {
                    "time_ms": problem.time_limit_ms,
                    "memory_mb": problem.memory_limit_mb,
                },
                "visible": problem.visible,
                "offline_enabled": problem.offline_enabled,
                "offline_policy": problem.offline_policy.model_dump(mode="json"),
                "judge": judge_config,
            }
            for problem, judge_config in problems
        ],
    }


def _export_fps(problems: list[tuple[Problem, dict[str, Any]]]) -> str:
    root = ET.Element("fps", {"version": "1.0", "generator": "gayoj"})
    for problem, judge_config in problems:
        item = ET.SubElement(root, "item")
        for key, value in {
            "id": problem.id,
            "title": problem.title,
            "type": problem.type,
            "difficulty": problem.difficulty,
            "description": problem.statement,
            "input": problem.input_format,
            "output": problem.output_format,
            "visible": "true" if problem.visible else "false",
            "offline_enabled": "true" if problem.offline_enabled else "false",
        }.items():
            ET.SubElement(item, key).text = str(value or "")
        ET.SubElement(item, "offline_policy").text = json.dumps(
            problem.offline_policy.model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if problem.time_limit_ms is not None:
            ET.SubElement(item, "time_limit", {"unit": "ms"}).text = str(problem.time_limit_ms)
        if problem.memory_limit_mb is not None:
            ET.SubElement(item, "memory_limit", {"unit": "mb"}).text = str(problem.memory_limit_mb)
        tags = ET.SubElement(item, "tags")
        for tag in problem.tags:
            ET.SubElement(tags, "tag").text = tag
        samples = ET.SubElement(item, "samples")
        for sample in problem.samples:
            sample_node = ET.SubElement(samples, "sample")
            ET.SubElement(sample_node, "input").text = str(sample.get("input", ""))
            ET.SubElement(sample_node, "output").text = str(sample.get("output", ""))
        options = ET.SubElement(item, "options")
        for option in problem.options:
            option_node = ET.SubElement(options, "option", {"key": str(option.get("key", ""))})
            option_node.text = str(option.get("text", ""))
        blanks = ET.SubElement(item, "blanks")
        for blank in problem.blanks:
            ET.SubElement(
                blanks,
                "blank",
                {
                    "key": str(blank.get("key", "")),
                    "label": str(blank.get("label", "")),
                    "score": str(blank.get("score", "")),
                },
            )
        ET.SubElement(item, "judge_config").text = json.dumps(judge_config, ensure_ascii=False, separators=(",", ":"))
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")


def _read_json_package(content: str) -> list[dict[str, Any]]:
    data = json.loads(content)
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("problems") or data.get("items") or data.get("data") or []
    else:
        raise ProblemPackageError("Problem package must be a JSON object or array")
    if not isinstance(items, list):
        raise ProblemPackageError("Problem package problems must be an array")
    return [item for item in items if isinstance(item, dict)]


def _read_qdu(content: str) -> list[dict[str, Any]]:
    items = []
    for raw in _read_json_package(content):
        items.append(
            {
                "id": raw.get("_id") or raw.get("id") or raw.get("display_id"),
                "title": raw.get("title"),
                "type": raw.get("problem_type") or raw.get("type"),
                "difficulty": raw.get("difficulty"),
                "tags": raw.get("tags"),
                "statement": raw.get("description") or raw.get("statement"),
                "input_format": raw.get("input_description") or raw.get("input_format"),
                "output_format": raw.get("output_description") or raw.get("output_format"),
                "samples": raw.get("samples"),
                "options": raw.get("options"),
                "blanks": raw.get("blanks"),
                "time_limit_ms": raw.get("time_limit_ms") or raw.get("time_limit"),
                "memory_limit_mb": raw.get("memory_limit_mb") or raw.get("memory_limit"),
                "visible": raw.get("visible", True),
                "offline_enabled": raw.get("offline_enabled", True),
                "offline_policy": raw.get("offline_policy") if isinstance(raw.get("offline_policy"), dict) else {},
                "judge_config": raw.get("judge_config") or raw.get("config") or {},
            }
        )
    return items


def _read_hydro(content: str) -> list[dict[str, Any]]:
    items = []
    for raw in _read_json_package(content):
        limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
        items.append(
            {
                "id": raw.get("pid") or raw.get("id") or raw.get("docId"),
                "title": raw.get("title"),
                "type": raw.get("type") or raw.get("problem_type"),
                "difficulty": raw.get("difficulty"),
                "tags": raw.get("tags"),
                "statement": raw.get("content") or raw.get("statement") or raw.get("description"),
                "input_format": raw.get("input") or raw.get("input_format"),
                "output_format": raw.get("output") or raw.get("output_format"),
                "samples": raw.get("samples"),
                "options": raw.get("options"),
                "blanks": raw.get("blanks"),
                "time_limit_ms": raw.get("time_limit_ms") or limits.get("time_ms") or limits.get("time"),
                "memory_limit_mb": raw.get("memory_limit_mb") or limits.get("memory_mb") or limits.get("memory"),
                "visible": raw.get("visible", True),
                "offline_enabled": raw.get("offline_enabled", True),
                "offline_policy": raw.get("offline_policy") if isinstance(raw.get("offline_policy"), dict) else {},
                "judge_config": raw.get("judge") or raw.get("judge_config") or raw.get("config") or {},
            }
        )
    return items


def _read_fps(content: str) -> list[dict[str, Any]]:
    root = ET.fromstring(content)
    items = root.findall(".//item") if root.tag != "item" else [root]
    raw_items = []
    for item in items:
        samples = []
        for sample in item.findall("./samples/sample") + item.findall("./sample"):
            samples.append({"input": _child_text(sample, "input"), "output": _child_text(sample, "output")})
        if not samples:
            sample_inputs = [_node_text(node) for node in item.findall("./sample_input")]
            sample_outputs = [_node_text(node) for node in item.findall("./sample_output")]
            for index, sample_input in enumerate(sample_inputs):
                samples.append({"input": sample_input, "output": sample_outputs[index] if index < len(sample_outputs) else ""})

        options = []
        for option in item.findall("./options/option") + item.findall("./option"):
            options.append(
                {
                    "key": option.attrib.get("key") or _child_text(option, "key"),
                    "text": _node_text(option) if option.text else _child_text(option, "text"),
                }
            )

        blanks = []
        for blank in item.findall("./blanks/blank") + item.findall("./blank"):
            blanks.append(
                {
                    "key": blank.attrib.get("key") or _child_text(blank, "key"),
                    "label": blank.attrib.get("label") or _child_text(blank, "label"),
                    "score": _int_or_none(blank.attrib.get("score") or _child_text(blank, "score")) or 100,
                }
            )

        judge_config_text = _child_text(item, "judge_config")
        offline_policy_text = _child_text(item, "offline_policy")
        try:
            judge_config = json.loads(judge_config_text) if judge_config_text.strip() else {}
            offline_policy = json.loads(offline_policy_text) if offline_policy_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise ProblemPackageError(f"Invalid FPS JSON field: {exc}") from exc
        raw_items.append(
            {
                "id": _child_text(item, "id"),
                "title": _child_text(item, "title"),
                "type": _child_text(item, "type"),
                "difficulty": _child_text(item, "difficulty"),
                "tags": [_node_text(tag) for tag in item.findall("./tags/tag") + item.findall("./tag")],
                "statement": _child_text(item, "description") or _child_text(item, "statement"),
                "input_format": _child_text(item, "input") or _child_text(item, "input_format"),
                "output_format": _child_text(item, "output") or _child_text(item, "output_format"),
                "samples": samples,
                "options": options,
                "blanks": blanks,
                "time_limit_ms": _int_or_none(_child_text(item, "time_limit")),
                "memory_limit_mb": _int_or_none(_child_text(item, "memory_limit")),
                "visible": _bool_value(_child_text(item, "visible"), True),
                "offline_enabled": _bool_value(_child_text(item, "offline_enabled"), True),
                "offline_policy": offline_policy if isinstance(offline_policy, dict) else {},
                "judge_config": judge_config,
            }
        )
    return raw_items


def _normalize_problem_payload(raw: dict[str, Any]) -> dict[str, Any]:
    problem_type = _problem_type(raw.get("type"))
    return {
        "title": _text(raw.get("title")),
        "type": problem_type,
        "difficulty": _difficulty(raw.get("difficulty")),
        "tags": _string_list(raw.get("tags")),
        "statement": _text(raw.get("statement")),
        "input_format": _text(raw.get("input_format")),
        "output_format": _text(raw.get("output_format")),
        "samples": _samples(raw.get("samples")),
        "options": _options(raw.get("options")) if problem_type in {"single_choice", "multiple_choice"} else [],
        "blanks": _blanks(raw.get("blanks")) if problem_type == "blank" else [],
        "time_limit_ms": _int_or_none(raw.get("time_limit_ms")),
        "memory_limit_mb": _int_or_none(raw.get("memory_limit_mb")),
        "visible": _bool_value(raw.get("visible"), True),
        "offline_enabled": _bool_value(raw.get("offline_enabled"), problem_type != "code"),
        "offline_policy": raw.get("offline_policy") if isinstance(raw.get("offline_policy"), dict) else {},
        "judge_config": raw.get("judge_config") if isinstance(raw.get("judge_config"), dict) else {},
    }


def _problem_type(value: Any) -> ProblemType:
    text = _text(value).lower().replace("-", "_").replace(" ", "_")
    mapping: dict[str, ProblemType] = {
        "code": "code",
        "programming": "code",
        "traditional": "code",
        "blank": "blank",
        "fill_blank": "blank",
        "fill": "blank",
        "single_choice": "single_choice",
        "single": "single_choice",
        "choice": "single_choice",
        "multiple_choice": "multiple_choice",
        "multi_choice": "multiple_choice",
        "multiple": "multiple_choice",
    }
    return mapping.get(text, "code")


def _difficulty(value: Any) -> str:
    text = _text(value)
    if text in _DIFFICULTIES:
        return text
    mapping = {
        "easy": "入门",
        "beginner": "入门",
        "basic": "基础",
        "medium": "提高",
        "normal": "基础",
        "hard": "困难",
    }
    return mapping.get(text.lower(), "基础")


def _samples(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    samples = []
    for item in value:
        if not isinstance(item, dict):
            continue
        samples.append({"input": _text(item.get("input")), "output": _text(item.get("output"))})
    return samples


def _options(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    options = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            key = _text(item.get("key") or item.get("label") or chr(65 + index))
            text = _text(item.get("text") or item.get("content") or item.get("value"))
        else:
            key = chr(65 + index)
            text = _text(item)
        if key and text:
            options.append({"key": key, "text": text})
    return options


def _blanks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    blanks = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            key = _text(item.get("key") or f"blank_{index + 1}")
            label = _text(item.get("label") or item.get("name") or key)
            score = _int_or_none(item.get("score")) or 100
        else:
            key = f"blank_{index + 1}"
            label = _text(item) or key
            score = 100
        if key and label:
            blanks.append({"key": key, "label": label, "score": score})
    return blanks


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.replace("，", ",").split(",")
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = _text(item)
        if text and text not in result:
            result.append(text)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _child_text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    return _node_text(child) if child is not None else ""


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _bool_value(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if not text:
        return default
    return text not in {"0", "false", "no", "off"}

