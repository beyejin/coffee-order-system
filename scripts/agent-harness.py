#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


class State(IntEnum):
    PASS = 0
    FAIL = 1
    BLOCKED = 2
    REPLAN_REQUIRED = 3


class HarnessViolation(Exception):
    def __init__(self, state: State, check_id: str, reason: str) -> None:
        self.state = state
        self.check_id = check_id
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Plan:
    issue: int
    target_branch: str
    objective: str
    allowed_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    declared_risks: tuple[str, ...]
    contract_changes: tuple[str, ...]
    non_goals: tuple[str, ...]
    relative_path: str
    plan_hash: str


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    patterns: tuple[str, ...]
    risks: tuple[str, ...]


@dataclass(frozen=True)
class RiskPolicy:
    schema_version: int
    known_risks: frozenset[str]
    rules: tuple[RiskRule, ...]
    protected_patterns: tuple[str, ...]
    risk_checks: Mapping[str, tuple[str, ...]]
    implemented_checks: frozenset[str]


PLAN_FIELDS = frozenset(
    {
        "issue",
        "targetBranch",
        "objective",
        "allowedPaths",
        "acceptanceCriteria",
        "declaredRisks",
        "contractChanges",
        "nonGoals",
    }
)
FORBIDDEN_PLAN_PATTERNS = frozenset(
    {
        "**",
        "src/**",
        "src/main/**",
        "src/main/java/**",
        "src/test/**",
        "docs/**",
        "harness/**",
        "scripts/**",
        ".github/**",
    }
)
POLICY_FIELDS = frozenset(
    {
        "schemaVersion",
        "knownRisks",
        "rules",
        "protectedPatterns",
        "riskChecks",
        "implementedChecks",
    }
)
RULE_FIELDS = frozenset({"id", "patterns", "risks"})


class _DuplicateJsonKey(ValueError):
    pass


def _reject_duplicate_json_keys(
    pairs: Sequence[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _violation(state: State, check_id: str, reason: str) -> HarnessViolation:
    return HarnessViolation(state, check_id, reason)


def string_array(
    raw: object,
    field: str,
    require_non_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise _violation(State.FAIL, "plan.schema", f"{field}는 문자열 배열이어야 합니다.")

    values: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value:
            raise _violation(
                State.FAIL,
                "plan.schema",
                f"{field}에는 빈 값이 아닌 문자열만 허용됩니다.",
            )
        if value != value.strip():
            raise _violation(
                State.FAIL,
                "plan.schema",
                f"{field} 값의 선행 또는 후행 공백은 허용되지 않습니다.",
            )
        values.append(value)

    if require_non_empty and not values:
        raise _violation(State.FAIL, "plan.schema", f"{field}는 비어 있을 수 없습니다.")
    if len(values) != len(set(values)):
        raise _violation(State.FAIL, "plan.schema", f"{field}에 중복 값이 있습니다.")
    return tuple(values)


def contract_change_path(declaration: str) -> str:
    path, separator, version = declaration.rpartition(" ")
    if (
        not separator
        or not path
        or any(character in path for character in "*?[]")
        or re.fullmatch(r"v[1-9]\d*", version) is None
    ):
        raise _violation(
            State.REPLAN_REQUIRED,
            "plan.contract-changes",
            "contractChanges는 '<정확한 경로> v<양의 정수>' 형식이어야 합니다.",
        )
    try:
        _validate_repository_pattern(path, "plan.contract-changes")
    except HarnessViolation as error:
        raise _violation(
            State.REPLAN_REQUIRED,
            "plan.contract-changes",
            "contractChanges는 '<정확한 경로> v<양의 정수>' 형식이어야 합니다.",
        ) from error
    return path


def validate_plan_pattern(pattern: str) -> None:
    if pattern in FORBIDDEN_PLAN_PATTERNS:
        raise _violation(
            State.REPLAN_REQUIRED,
            "plan.scope",
            f"광범위한 allowedPaths pattern은 허용되지 않습니다: {pattern}",
        )
    _validate_repository_pattern(pattern, "plan.schema")


def _validate_repository_pattern(pattern: str, check_id: str) -> None:
    body = pattern[:-3] if pattern.endswith("/**") else pattern
    segments = body.split("/")
    if (
        pattern != pattern.strip()
        or pattern.startswith("/")
        or "\\" in pattern
        or "//" in pattern
        or any(unicodedata.category(character) == "Cc" for character in pattern)
        or not body
        or body.endswith("/")
        or any(segment in {"", ".", ".."} for segment in segments)
    ):
        raise _violation(
            State.FAIL,
            check_id,
            f"저장소 상대 경로만 허용됩니다: {pattern}",
        )

    if any(character in body for character in "*?[]"):
        raise _violation(
            State.FAIL,
            check_id,
            f"정확한 경로 또는 trailing /** pattern만 허용됩니다: {pattern}",
        )


def path_matches(pattern: str, path: str) -> bool:
    if not pattern.endswith("/**"):
        return pattern == path
    directory = pattern[:-3].rstrip("/")
    return path == directory or path.startswith(f"{directory}/")


def _parse_json_object(raw: bytes, check_id: str, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except _DuplicateJsonKey as error:
        raise _violation(
            State.FAIL,
            check_id,
            f"{label} JSON에 중복 key가 있습니다: {error}",
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _violation(State.FAIL, check_id, f"{label} JSON을 해석할 수 없습니다: {error}") from error
    if not isinstance(payload, dict):
        raise _violation(State.FAIL, check_id, f"{label} 최상위 값은 object여야 합니다.")
    return payload


def _non_empty_string(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise _violation(State.FAIL, "plan.schema", f"{field}는 빈 값이 아닌 문자열이어야 합니다.")
    if raw != raw.strip():
        raise _violation(
            State.FAIL,
            "plan.schema",
            f"{field} 값의 선행 또는 후행 공백은 허용되지 않습니다.",
        )
    return raw


def parse_plan(
    raw: bytes,
    relative_path: str,
    known_risks: Iterable[str],
) -> Plan:
    payload = _parse_json_object(raw, "plan.schema", "plan")
    actual_fields = set(payload)
    unknown_fields = actual_fields - PLAN_FIELDS
    missing_fields = PLAN_FIELDS - actual_fields
    if unknown_fields:
        raise _violation(
            State.FAIL,
            "plan.schema",
            f"미지원 필드가 있습니다: {sorted(unknown_fields)}",
        )
    if missing_fields:
        raise _violation(
            State.FAIL,
            "plan.schema",
            f"필수 필드가 없습니다: {sorted(missing_fields)}",
        )

    issue = payload["issue"]
    if type(issue) is not int or issue < 1:
        raise _violation(State.FAIL, "plan.schema", "issue는 1 이상의 정수여야 합니다.")

    target_branch = _non_empty_string(payload["targetBranch"], "targetBranch")
    if target_branch != "main":
        raise _violation(
            State.REPLAN_REQUIRED,
            "plan.target",
            "targetBranch는 main이어야 합니다.",
        )

    expected_path = f"harness/plans/{issue}.json"
    if relative_path != expected_path:
        raise _violation(
            State.FAIL,
            "plan.path",
            f"plan 경로는 {expected_path}여야 합니다.",
        )

    objective = _non_empty_string(payload["objective"], "objective")
    allowed_paths = string_array(payload["allowedPaths"], "allowedPaths", True)
    for pattern in allowed_paths:
        validate_plan_pattern(pattern)

    acceptance_criteria = string_array(
        payload["acceptanceCriteria"],
        "acceptanceCriteria",
        True,
    )
    declared_risks = string_array(payload["declaredRisks"], "declaredRisks", False)
    unknown_risks = set(declared_risks) - set(known_risks)
    if unknown_risks:
        raise _violation(
            State.FAIL,
            "plan.schema",
            f"declaredRisks에 알 수 없는 값이 있습니다: {sorted(unknown_risks)}",
        )

    contract_changes = string_array(
        payload["contractChanges"],
        "contractChanges",
        False,
    )
    for declaration in contract_changes:
        contract_change_path(declaration)
    non_goals = string_array(payload["nonGoals"], "nonGoals", True)

    return Plan(
        issue=issue,
        target_branch=target_branch,
        objective=objective,
        allowed_paths=allowed_paths,
        acceptance_criteria=acceptance_criteria,
        declared_risks=declared_risks,
        contract_changes=contract_changes,
        non_goals=non_goals,
        relative_path=relative_path,
        plan_hash=hashlib.sha256(raw).hexdigest(),
    )


def policy_error(reason: str) -> HarnessViolation:
    return HarnessViolation(State.FAIL, "policy.schema", reason)


def policy_string_array(
    raw: object,
    field: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise policy_error(f"{field}는 문자열 배열이어야 합니다.")
    values: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not value:
            raise policy_error(f"{field}에는 빈 값이 아닌 문자열만 허용됩니다.")
        if value != value.strip():
            raise policy_error(f"{field} 값의 선행 또는 후행 공백은 허용되지 않습니다.")
        values.append(value)
    if not allow_empty and not values:
        raise policy_error(f"{field}는 비어 있을 수 없습니다.")
    if len(values) != len(set(values)):
        raise policy_error(f"{field}에 중복 값이 있습니다.")
    return tuple(values)


def validate_policy_pattern(pattern: str) -> None:
    try:
        _validate_repository_pattern(pattern, "policy.schema")
    except HarnessViolation as error:
        raise policy_error(error.reason) from error


def load_risk_policy(path: Path) -> RiskPolicy:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise policy_error(f"risk policy를 읽을 수 없습니다: {error}") from error
    try:
        payload = _parse_json_object(raw, "policy.schema", "risk policy")
    except HarnessViolation as error:
        raise policy_error(error.reason) from error

    actual_fields = set(payload)
    if actual_fields != POLICY_FIELDS:
        unknown_fields = actual_fields - POLICY_FIELDS
        missing_fields = POLICY_FIELDS - actual_fields
        raise policy_error(
            "최상위 필드가 정확하지 않습니다: "
            f"unknown={sorted(unknown_fields)}, missing={sorted(missing_fields)}"
        )

    schema_version = payload["schemaVersion"]
    if type(schema_version) is not int or schema_version != 1:
        raise policy_error("schemaVersion은 정수 1이어야 합니다.")

    known_risk_values = policy_string_array(payload["knownRisks"], "knownRisks")
    known_risks = frozenset(known_risk_values)

    raw_rules = payload["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise policy_error("rules는 비어 있지 않은 배열이어야 합니다.")

    rules: list[RiskRule] = []
    rule_ids: set[str] = set()
    all_patterns: set[str] = set()
    for index, raw_rule in enumerate(raw_rules):
        if not isinstance(raw_rule, dict) or set(raw_rule) != RULE_FIELDS:
            raise policy_error(f"rules[{index}] 필드는 id, patterns, risks여야 합니다.")

        rule_id = raw_rule["id"]
        if not isinstance(rule_id, str) or not rule_id:
            raise policy_error(f"rules[{index}].id는 빈 값이 아닌 문자열이어야 합니다.")
        if rule_id != rule_id.strip():
            raise policy_error(
                f"rules[{index}].id의 선행 또는 후행 공백은 허용되지 않습니다."
            )
        if rule_id in rule_ids:
            raise policy_error(f"중복 rule id가 있습니다: {rule_id}")
        rule_ids.add(rule_id)

        patterns = policy_string_array(raw_rule["patterns"], f"rules[{index}].patterns")
        for pattern in patterns:
            validate_policy_pattern(pattern)
            if pattern in all_patterns:
                raise policy_error(f"중복 pattern이 있습니다: {pattern}")
            all_patterns.add(pattern)

        risks = policy_string_array(
            raw_rule["risks"],
            f"rules[{index}].risks",
            allow_empty=True,
        )
        unknown_risks = set(risks) - known_risks
        if unknown_risks:
            raise policy_error(
                f"rules[{index}].risks에 알 수 없는 값이 있습니다: {sorted(unknown_risks)}"
            )
        rules.append(RiskRule(rule_id=rule_id, patterns=patterns, risks=risks))

    protected_patterns = policy_string_array(
        payload["protectedPatterns"],
        "protectedPatterns",
    )
    for pattern in protected_patterns:
        validate_policy_pattern(pattern)

    raw_risk_checks = payload["riskChecks"]
    if not isinstance(raw_risk_checks, dict) or set(raw_risk_checks) != known_risks:
        raise policy_error("riskChecks key는 knownRisks와 정확히 일치해야 합니다.")
    risk_checks: dict[str, tuple[str, ...]] = {}
    all_check_ids: set[str] = set()
    for risk in known_risk_values:
        checks = policy_string_array(raw_risk_checks[risk], f"riskChecks.{risk}")
        duplicates = all_check_ids.intersection(checks)
        if duplicates:
            raise policy_error(f"riskChecks에 중복 check id가 있습니다: {sorted(duplicates)}")
        all_check_ids.update(checks)
        risk_checks[risk] = checks

    implemented_check_values = policy_string_array(
        payload["implementedChecks"],
        "implementedChecks",
    )
    unknown_implemented_checks = set(implemented_check_values) - all_check_ids
    if unknown_implemented_checks:
        raise policy_error(
            "implementedChecks에 riskChecks에 없는 값이 있습니다: "
            f"{sorted(unknown_implemented_checks)}"
        )

    return RiskPolicy(
        schema_version=schema_version,
        known_risks=known_risks,
        rules=tuple(rules),
        protected_patterns=protected_patterns,
        risk_checks=risk_checks,
        implemented_checks=frozenset(implemented_check_values),
    )


def load_plan(root: Path, plan_path: Path, policy: RiskPolicy) -> Plan:
    resolved_root = root.resolve()
    candidate = plan_path if plan_path.is_absolute() else resolved_root / plan_path
    try:
        resolved_plan = candidate.resolve(strict=True)
        relative_path = resolved_plan.relative_to(resolved_root).as_posix()
        raw = resolved_plan.read_bytes()
    except (OSError, ValueError) as error:
        raise _violation(
            State.FAIL,
            "plan.path",
            f"plan을 저장소 내부 경로에서 읽을 수 없습니다: {error}",
        ) from error
    return parse_plan(raw, relative_path, policy.known_risks)
