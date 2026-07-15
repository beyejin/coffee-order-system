#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
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


@dataclass(frozen=True)
class RiskClassification:
    detected_risks: tuple[str, ...]
    unclassified_paths: tuple[str, ...]


@dataclass(frozen=True)
class GitContext:
    branch: str
    target_branch: str
    base_tip_sha: str
    merge_base_sha: str
    candidate_head_sha: str
    tested_revision_sha: str


@dataclass(frozen=True)
class PlanLock:
    schema_version: int
    issue: int
    plan_path: str
    plan_hash: str
    target_branch: str
    branch: str
    base_tip_sha: str
    merge_base_sha: str


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    state: State
    reason: str
    command: tuple[str, ...] = ()
    exit_code: int | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class Evaluation:
    schema_version: int
    state: State
    base_tip_sha: str | None
    merge_base_sha: str | None
    candidate_head_sha: str | None
    tested_revision_sha: str | None
    plan_path: str
    plan_hash: str | None
    declared_risks: tuple[str, ...]
    detected_risks: tuple[str, ...]
    changed_paths: tuple[str, ...]
    diff_hash: str | None
    checks: tuple[CheckResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "state": self.state.name,
            "baseTipSha": self.base_tip_sha,
            "mergeBaseSha": self.merge_base_sha,
            "candidateHeadSha": self.candidate_head_sha,
            "testedRevisionSha": self.tested_revision_sha,
            "planPath": self.plan_path,
            "planHash": self.plan_hash,
            "declaredRisks": list(self.declared_risks),
            "detectedRisks": list(self.detected_risks),
            "changedPaths": list(self.changed_paths),
            "diffHash": self.diff_hash,
            "checks": [
                {
                    "id": check.check_id,
                    "state": check.state.name,
                    "reason": check.reason,
                    "command": list(check.command),
                    "exitCode": check.exit_code,
                    "durationMs": check.duration_ms,
                }
                for check in self.checks
            ],
        }


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
PLAN_LOCK_FIELDS = frozenset(
    {
        "schemaVersion",
        "issue",
        "planPath",
        "planHash",
        "targetBranch",
        "branch",
        "baseTipSha",
        "mergeBaseSha",
    }
)
BRANCH_PATTERN = re.compile(
    r"^(feature|fix|refactor|docs)/([1-9][0-9]*)-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)
LEGACY_PLAN_PATH_PATTERN = re.compile(
    r"^harness/plans/([1-9][0-9]*)\.json$"
)
READABLE_PLAN_PATH_PATTERN = re.compile(
    r"^harness/plans/issue-([1-9][0-9]*)-[a-z0-9]+(?:-[a-z0-9]+)*\.json$"
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PLAN_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_PREFLIGHT_CHECK_IDS = frozenset(
    {
        "environment.python",
        "environment.java",
        "environment.docker",
        "environment.java17-toolchain",
    }
)
STATE_PRIORITY = {
    State.PASS: 0,
    State.BLOCKED: 1,
    State.FAIL: 2,
    State.REPLAN_REQUIRED: 3,
}
HARNESS_TEST_COMMAND = (
    sys.executable,
    "-m",
    "unittest",
    "discover",
    "-s",
    "harness/tests",
    "-p",
    "test_*.py",
    "-v",
)
GRADLE_TEST_COMMAND = ("./gradlew", "clean", "test", "--console", "plain")
INLINE_CHECK_IDS = frozenset(
    {"scope.allowed-paths", "risk.classification", "risk.declaration"}
)
DOMAIN_ORACLE_CHECK_IDS = frozenset(
    {
        "oracle.architecture",
        "oracle.api-contract",
        "oracle.migration-fresh",
        "oracle.migration-upgrade",
        "oracle.transaction",
        "oracle.cross-domain-concurrency",
        "oracle.async-isolation",
        "oracle.multi-instance",
    }
)
ORACLE_SCRIPT_PATH = "scripts/harness-oracles.py"


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


def aggregate_state(checks: Iterable[CheckResult]) -> State:
    return max(
        (check.state for check in checks),
        key=STATE_PRIORITY.__getitem__,
        default=State.PASS,
    )


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


def plan_path_matches_issue(relative_path: str, issue: int) -> bool:
    for pattern in (LEGACY_PLAN_PATH_PATTERN, READABLE_PLAN_PATH_PATTERN):
        match = pattern.fullmatch(relative_path)
        if match is not None:
            return int(match.group(1)) == issue
    return False


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

    if not plan_path_matches_issue(relative_path, issue):
        raise _violation(
            State.FAIL,
            "plan.path",
            "plan 경로는 harness/plans/{issue}.json 또는 "
            "harness/plans/issue-{issue}-<slug>.json이어야 합니다.",
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
    runtime_check_ids = (
        set(INLINE_CHECK_IDS)
        | {"harness.unit", "gradle.test"}
        | set(DOMAIN_ORACLE_CHECK_IDS)
    )
    unsupported_runtime_checks = set(implemented_check_values) - runtime_check_ids
    if unsupported_runtime_checks:
        raise policy_error(
            "implementedChecks에 실행기가 없는 값이 있습니다: "
            f"{sorted(unsupported_runtime_checks)}"
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


def validate_branch(branch: str, issue: int) -> None:
    match = BRANCH_PATTERN.fullmatch(branch)
    if match is None:
        raise _violation(
            State.REPLAN_REQUIRED,
            "git.branch",
            "branch는 feature|fix|refactor|docs/<issue>-<lowercase-kebab> "
            f"형식이어야 합니다: {branch or '<detached>'}",
        )

    branch_issue = int(match.group(2))
    if branch_issue != issue:
        raise _violation(
            State.REPLAN_REQUIRED,
            "git.branch",
            f"branch issue 번호 {branch_issue}와 plan issue 번호 {issue}가 다릅니다.",
        )


def _decode_git_output(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace").strip()


def run_git(root: Path, *args: str) -> bytes:
    command = ("git", *args)
    try:
        result = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise _violation(
            State.BLOCKED,
            "git.repository",
            f"git 명령을 실행할 수 없습니다: {error}",
        ) from error

    if result.returncode != 0:
        detail = _decode_git_output(result.stderr) or "명령 실행 실패"
        raise _violation(
            State.BLOCKED,
            "git.repository",
            f"{' '.join(command)} 실패: {detail}",
        )
    return result.stdout


def find_git_root(start: Path) -> Path:
    raw = run_git(start, "rev-parse", "--show-toplevel")
    root = raw.decode("utf-8", errors="surrogateescape").strip()
    if not root:
        raise _violation(
            State.BLOCKED,
            "git.repository",
            "git 저장소 루트를 찾을 수 없습니다.",
        )
    return Path(root).resolve()


def resolve_local_git_context(root: Path, plan: Plan) -> GitContext:
    try:
        run_git(root, "fetch", "--quiet", "origin", plan.target_branch)
    except HarnessViolation as error:
        raise _violation(
            State.BLOCKED,
            "git.base",
            f"origin/{plan.target_branch} fetch 실패: {error.reason}",
        ) from error

    branch = run_git(root, "branch", "--show-current").decode(
        "utf-8",
        errors="surrogateescape",
    ).strip()
    if not branch:
        raise _violation(
            State.REPLAN_REQUIRED,
            "git.branch",
            "detached HEAD에서는 prepare를 실행할 수 없습니다.",
        )
    validate_branch(branch, plan.issue)

    base_ref = f"refs/remotes/origin/{plan.target_branch}"
    base_tip_sha = _decode_git_output(run_git(root, "rev-parse", base_ref))
    merge_base_sha = _decode_git_output(
        run_git(root, "merge-base", "HEAD", base_tip_sha)
    )
    candidate_head_sha = _decode_git_output(run_git(root, "rev-parse", "HEAD"))

    identities = {
        "base tip": base_tip_sha,
        "merge-base": merge_base_sha,
        "HEAD": candidate_head_sha,
    }
    malformed = [label for label, sha in identities.items() if not SHA_PATTERN.fullmatch(sha)]
    if malformed:
        raise _violation(
            State.FAIL,
            "git.base",
            f"유효한 lowercase 40자리 SHA가 아닙니다: {', '.join(malformed)}",
        )

    return GitContext(
        branch=branch,
        target_branch=plan.target_branch,
        base_tip_sha=base_tip_sha,
        merge_base_sha=merge_base_sha,
        candidate_head_sha=candidate_head_sha,
        tested_revision_sha=candidate_head_sha,
    )


def _git_diff_error(reason: str) -> HarnessViolation:
    return _violation(State.FAIL, "git.diff", reason)


def _decode_git_path(raw: bytes) -> str:
    if not raw:
        raise _git_diff_error("git diff path가 비어 있습니다.")
    return raw.decode("utf-8", errors="surrogateescape")


def parse_name_status(raw: bytes) -> tuple[str, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\0"):
        raise _git_diff_error("git name-status token stream이 NUL로 끝나지 않습니다.")

    tokens = raw[:-1].split(b"\0")
    paths: list[str] = []
    index = 0
    while index < len(tokens):
        raw_status = tokens[index]
        index += 1
        try:
            status = raw_status.decode("ascii")
        except UnicodeDecodeError as error:
            raise _git_diff_error("git name-status 상태값은 ASCII여야 합니다.") from error
        if re.fullmatch(r"(?:[ACDMTUXB]|[RC][0-9]{0,3})", status) is None:
            raise _git_diff_error(f"알 수 없는 git name-status 상태값입니다: {status}")

        path_count = 2 if status.startswith(("R", "C")) else 1
        if index + path_count > len(tokens):
            raise _git_diff_error("git name-status token stream이 불완전합니다.")
        for _ in range(path_count):
            paths.append(_decode_git_path(tokens[index]))
            index += 1

    return tuple(paths)


def parse_nul_paths(raw: bytes) -> tuple[str, ...]:
    if not raw:
        return ()
    if not raw.endswith(b"\0"):
        raise _git_diff_error("git path token stream이 NUL로 끝나지 않습니다.")
    return tuple(_decode_git_path(token) for token in raw[:-1].split(b"\0"))


def collect_worktree_paths(root: Path) -> tuple[str, ...]:
    cached = parse_name_status(
        run_git(
            root,
            "diff",
            "--cached",
            "--name-status",
            "-z",
            "--find-renames",
        )
    )
    unstaged = parse_name_status(
        run_git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
        )
    )
    untracked = parse_nul_paths(
        run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    )
    return tuple(sorted(set(cached) | set(unstaged) | set(untracked)))


def collect_local_changed_paths(
    root: Path,
    merge_base_sha: str,
) -> tuple[str, ...]:
    committed = parse_name_status(
        run_git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies-harder",
            merge_base_sha,
            "HEAD",
            "--",
        )
    )
    cached = parse_name_status(
        run_git(
            root,
            "diff",
            "--cached",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies-harder",
            "--",
        )
    )
    unstaged = parse_name_status(
        run_git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies-harder",
            "--",
        )
    )
    untracked = parse_nul_paths(
        run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    )
    return tuple(
        sorted(set(committed) | set(cached) | set(unstaged) | set(untracked))
    )


def compute_diff_hash(
    root: Path,
    context: GitContext,
    changed_paths: Iterable[str],
) -> str:
    try:
        raw_diff = run_git(
            root,
            "diff",
            "--binary",
            "--no-ext-diff",
            "--no-textconv",
            context.merge_base_sha,
            "--",
        )
        untracked_paths = set(
            parse_nul_paths(
                run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
            )
        )
    except HarnessViolation:
        raise
    except Exception as error:
        raise _git_diff_error(f"diff hash 입력을 읽을 수 없습니다: {error}") from error

    selected_untracked = sorted(untracked_paths.intersection(set(changed_paths)))
    digest = hashlib.sha256()
    digest.update(raw_diff)
    resolved_root = root.resolve()

    for relative_path in selected_untracked:
        candidate = resolved_root / relative_path
        try:
            status_result = candidate.lstat()
            if stat.S_ISLNK(status_result.st_mode):
                content = os.readlink(candidate).encode(
                    "utf-8",
                    errors="surrogateescape",
                )
            elif stat.S_ISREG(status_result.st_mode):
                candidate.resolve(strict=True).relative_to(resolved_root)
                content = candidate.read_bytes()
            else:
                raise OSError("regular file 또는 symlink가 아닙니다.")
        except (OSError, ValueError) as error:
            raise _git_diff_error(
                f"untracked diff 내용을 읽을 수 없습니다: {relative_path!r}: {error}"
            ) from error

        digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")

    return digest.hexdigest()


def scope_violations(
    changed_paths: Iterable[str],
    plan: Plan,
) -> tuple[str, ...]:
    violations = {
        path
        for path in changed_paths
        if path != plan.relative_path
        and not any(path_matches(pattern, path) for pattern in plan.allowed_paths)
    }
    return tuple(sorted(violations))


def classify_risks(
    changed_paths: Iterable[str],
    policy: RiskPolicy,
    plan_path: str = "",
) -> RiskClassification:
    detected_risks: set[str] = set()
    unclassified_paths: list[str] = []

    for path in sorted(set(changed_paths)):
        if path == plan_path:
            continue

        matched = False
        for rule in policy.rules:
            if any(path_matches(pattern, path) for pattern in rule.patterns):
                matched = True
                detected_risks.update(rule.risks)
        if not matched:
            unclassified_paths.append(path)

    return RiskClassification(
        detected_risks=tuple(sorted(detected_risks)),
        unclassified_paths=tuple(unclassified_paths),
    )


def validate_risk_declarations(
    plan: Plan,
    classification: RiskClassification,
) -> None:
    if classification.unclassified_paths:
        rendered_paths = ", ".join(
            repr(path) for path in classification.unclassified_paths
        )
        raise _violation(
            State.REPLAN_REQUIRED,
            "risk.classification",
            f"미분류 경로가 있습니다: {rendered_paths}",
        )

    undeclared_risks = sorted(
        set(classification.detected_risks) - set(plan.declared_risks)
    )
    if undeclared_risks:
        raise _violation(
            State.REPLAN_REQUIRED,
            "risk.declaration",
            f"감지되었지만 미선언된 위험이 있습니다: {undeclared_risks}",
        )


def validate_contract_changes(
    changed_paths: Iterable[str],
    plan: Plan,
    policy: RiskPolicy,
) -> None:
    declared_paths = {
        contract_change_path(declaration) for declaration in plan.contract_changes
    }
    undeclared_protected_paths = sorted(
        {
            path
            for path in changed_paths
            if path != plan.relative_path
            and any(
                path_matches(pattern, path)
                for pattern in policy.protected_patterns
            )
            and path not in declared_paths
        }
    )
    if undeclared_protected_paths:
        rendered_paths = ", ".join(
            repr(path) for path in undeclared_protected_paths
        )
        raise _violation(
            State.REPLAN_REQUIRED,
            "trust-root.contract",
            f"보호 경로의 정확한 contractChanges 선언이 없습니다: {rendered_paths}",
        )


def validate_existing_migrations_immutable(
    root: Path,
    context: GitContext,
    changed_paths: Iterable[str],
) -> None:
    migration_prefix = "src/main/resources/db/migration/"
    reported_changed_paths = set(changed_paths)
    base_migrations = set(
        parse_nul_paths(
            run_git(
                root,
                "ls-tree",
                "-r",
                "-z",
                "--name-only",
                context.merge_base_sha,
                "--",
                migration_prefix,
            )
        )
    )
    committed_mutations = parse_name_status(
        run_git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            context.merge_base_sha,
            "HEAD",
            "--",
            migration_prefix,
        )
    )
    cached_mutations = parse_name_status(
        run_git(
            root,
            "diff",
            "--cached",
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--",
            migration_prefix,
        )
    )
    unstaged_mutations = parse_name_status(
        run_git(
            root,
            "diff",
            "--name-status",
            "-z",
            "--no-renames",
            "--no-ext-diff",
            "--",
            migration_prefix,
        )
    )
    actual_mutation_paths = (
        set(committed_mutations) | set(cached_mutations) | set(unstaged_mutations)
    )
    missing_reported_paths = sorted(
        actual_mutation_paths - reported_changed_paths
    )
    if missing_reported_paths:
        rendered_paths = ", ".join(repr(path) for path in missing_reported_paths)
        raise _git_diff_error(
            f"전체 diff 수집에서 실제 migration 변경 경로가 누락되었습니다: {rendered_paths}"
        )

    modified_existing_migrations = sorted(
        base_migrations.intersection(actual_mutation_paths)
    )
    if modified_existing_migrations:
        rendered_paths = ", ".join(
            repr(path) for path in modified_existing_migrations
        )
        raise _violation(
            State.FAIL,
            "migration.immutable",
            f"기존 Flyway migration은 수정, 삭제, rename할 수 없습니다: {rendered_paths}",
        )


def _evidence_path_error(reason: str) -> HarnessViolation:
    return _violation(State.FAIL, "evidence.path", reason)


def _strict_repository_root(root: Path) -> Path:
    try:
        resolved_root = root.resolve(strict=True)
        root_status = resolved_root.lstat()
    except OSError as error:
        raise _evidence_path_error(
            f"repository root를 확인할 수 없습니다: {error}"
        ) from error
    if not stat.S_ISDIR(root_status.st_mode):
        raise _evidence_path_error("repository root는 directory여야 합니다.")
    return resolved_root


def _ensure_safe_evidence_directory(root: Path, directory: Path) -> None:
    try:
        directory_status = directory.lstat()
    except FileNotFoundError:
        try:
            directory.mkdir()
        except FileExistsError:
            pass
        except OSError as error:
            raise _evidence_path_error(
                f"evidence directory를 생성할 수 없습니다: {directory}: {error}"
            ) from error
        try:
            directory_status = directory.lstat()
        except OSError as error:
            raise _evidence_path_error(
                f"생성한 evidence directory를 확인할 수 없습니다: {directory}: {error}"
            ) from error
    except OSError as error:
        raise _evidence_path_error(
            f"evidence directory를 확인할 수 없습니다: {directory}: {error}"
        ) from error

    if stat.S_ISLNK(directory_status.st_mode):
        raise _evidence_path_error(
            f"evidence directory symlink는 허용되지 않습니다: {directory}"
        )
    if not stat.S_ISDIR(directory_status.st_mode):
        raise _evidence_path_error(
            f"evidence 경로는 directory여야 합니다: {directory}"
        )

    try:
        resolved_directory = directory.resolve(strict=True)
        resolved_directory.relative_to(root)
    except (OSError, ValueError) as error:
        raise _evidence_path_error(
            f"evidence directory는 repository 내부여야 합니다: {directory}"
        ) from error


def _safe_evidence_path(root: Path, filename: str) -> Path:
    resolved_root = _strict_repository_root(root)
    build_directory = resolved_root / "build"
    harness_directory = build_directory / "harness"

    _ensure_safe_evidence_directory(resolved_root, build_directory)
    _ensure_safe_evidence_directory(resolved_root, harness_directory)
    path = harness_directory / filename
    try:
        target_status = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as error:
        raise _evidence_path_error(
            f"evidence file을 확인할 수 없습니다: {path}: {error}"
        ) from error

    if stat.S_ISLNK(target_status.st_mode):
        raise _evidence_path_error(f"evidence file symlink는 허용되지 않습니다: {path}")
    if not stat.S_ISREG(target_status.st_mode):
        raise _evidence_path_error(f"evidence file은 regular file이어야 합니다: {path}")
    return path


def safe_evidence_lock_path(root: Path) -> Path:
    return _safe_evidence_path(root, "plan.lock.json")


def safe_evidence_evaluation_path(root: Path) -> Path:
    return _safe_evidence_path(root, "evaluation.json")


def _remove_stale_evidence(path: Path, label: str) -> Path:
    try:
        path_status = path.lstat()
    except FileNotFoundError:
        return path
    except OSError as error:
        raise _evidence_path_error(f"기존 {label}을 확인할 수 없습니다: {error}") from error

    if stat.S_ISLNK(path_status.st_mode) or not stat.S_ISREG(path_status.st_mode):
        raise _evidence_path_error(f"{label} 경로는 regular file이어야 합니다.")
    try:
        path.unlink()
    except OSError as error:
        raise _evidence_path_error(f"기존 {label}을 제거할 수 없습니다: {error}") from error
    return path


def remove_stale_plan_lock(root: Path) -> Path:
    lock_path = safe_evidence_lock_path(root)
    return _remove_stale_evidence(lock_path, "plan lock")


def remove_stale_evaluation(root: Path) -> Path:
    evaluation_path = safe_evidence_evaluation_path(root)
    return _remove_stale_evidence(evaluation_path, "evaluation")


def write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ) + "\n"
    try:
        encoded = rendered.encode("utf-8")
    except UnicodeEncodeError:
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode("utf-8")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def plan_lock_payload(lock: PlanLock) -> dict[str, object]:
    return {
        "schemaVersion": lock.schema_version,
        "issue": lock.issue,
        "planPath": lock.plan_path,
        "planHash": lock.plan_hash,
        "targetBranch": lock.target_branch,
        "branch": lock.branch,
        "baseTipSha": lock.base_tip_sha,
        "mergeBaseSha": lock.merge_base_sha,
    }


def make_plan_lock(plan: Plan, context: GitContext) -> PlanLock:
    return PlanLock(
        schema_version=1,
        issue=plan.issue,
        plan_path=plan.relative_path,
        plan_hash=plan.plan_hash,
        target_branch=plan.target_branch,
        branch=context.branch,
        base_tip_sha=context.base_tip_sha,
        merge_base_sha=context.merge_base_sha,
    )


def _plan_lock_error(reason: str) -> HarnessViolation:
    return _violation(State.REPLAN_REQUIRED, "plan.lock", reason)


def _lock_string(raw: object, field: str) -> str:
    if not isinstance(raw, str) or not raw:
        raise _plan_lock_error(f"{field}는 빈 값이 아닌 문자열이어야 합니다.")
    if raw != raw.strip() or any(
        unicodedata.category(character) == "Cc" for character in raw
    ):
        raise _plan_lock_error(f"{field}에 신뢰할 수 없는 whitespace가 있습니다.")
    return raw


def load_plan_lock(path: Path) -> PlanLock:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise _plan_lock_error(f"plan lock을 읽을 수 없습니다: {error}") from error

    try:
        payload = _parse_json_object(raw, "plan.lock", "plan lock")
    except HarnessViolation as error:
        raise _plan_lock_error(error.reason) from error

    if set(payload) != PLAN_LOCK_FIELDS:
        unknown = set(payload) - PLAN_LOCK_FIELDS
        missing = PLAN_LOCK_FIELDS - set(payload)
        raise _plan_lock_error(
            "plan lock 필드가 정확하지 않습니다: "
            f"unknown={sorted(unknown)}, missing={sorted(missing)}"
        )

    schema_version = payload["schemaVersion"]
    issue = payload["issue"]
    if type(schema_version) is not int or schema_version != 1:
        raise _plan_lock_error("schemaVersion은 정수 1이어야 합니다.")
    if type(issue) is not int or issue < 1:
        raise _plan_lock_error("issue는 1 이상의 정수여야 합니다.")

    plan_path = _lock_string(payload["planPath"], "planPath")
    plan_hash = _lock_string(payload["planHash"], "planHash")
    target_branch = _lock_string(payload["targetBranch"], "targetBranch")
    branch = _lock_string(payload["branch"], "branch")
    base_tip_sha = _lock_string(payload["baseTipSha"], "baseTipSha")
    merge_base_sha = _lock_string(payload["mergeBaseSha"], "mergeBaseSha")

    if not plan_path_matches_issue(plan_path, issue):
        raise _plan_lock_error(
            "planPath는 harness/plans/{issue}.json 또는 "
            "harness/plans/issue-{issue}-<slug>.json이어야 합니다."
        )
    if target_branch != "main":
        raise _plan_lock_error("targetBranch는 main이어야 합니다.")
    try:
        validate_branch(branch, issue)
    except HarnessViolation as error:
        raise _plan_lock_error(error.reason) from error
    if PLAN_HASH_PATTERN.fullmatch(plan_hash) is None:
        raise _plan_lock_error("planHash는 lowercase 64자리 hex여야 합니다.")
    if SHA_PATTERN.fullmatch(base_tip_sha) is None:
        raise _plan_lock_error("baseTipSha는 lowercase 40자리 SHA여야 합니다.")
    if SHA_PATTERN.fullmatch(merge_base_sha) is None:
        raise _plan_lock_error("mergeBaseSha는 lowercase 40자리 SHA여야 합니다.")

    return PlanLock(
        schema_version=schema_version,
        issue=issue,
        plan_path=plan_path,
        plan_hash=plan_hash,
        target_branch=target_branch,
        branch=branch,
        base_tip_sha=base_tip_sha,
        merge_base_sha=merge_base_sha,
    )


def validate_plan_lock(lock: PlanLock, plan: Plan, context: GitContext) -> None:
    comparisons = (
        ("issue", lock.issue, plan.issue),
        ("plan path", lock.plan_path, plan.relative_path),
        ("plan hash", lock.plan_hash, plan.plan_hash),
        ("target branch", lock.target_branch, plan.target_branch),
        ("branch", lock.branch, context.branch),
        ("base tip", lock.base_tip_sha, context.base_tip_sha),
        ("merge-base", lock.merge_base_sha, context.merge_base_sha),
    )
    changed = [label for label, locked, current in comparisons if locked != current]
    if changed:
        raise _plan_lock_error(f"prepare 이후 변경됨: {', '.join(changed)}")


def _last_output(stdout: bytes, stderr: bytes) -> str:
    combined = stdout + stderr
    return combined.decode("utf-8", errors="replace")[-4000:].strip()


def blocked_environment_check(
    root: Path,
    check_id: str,
    command: Sequence[str],
) -> CheckResult:
    normalized_command = tuple(command)
    started = time.monotonic()
    try:
        result = subprocess.run(
            normalized_command,
            cwd=root,
            check=False,
            capture_output=True,
        )
    except OSError as error:
        duration_ms = int((time.monotonic() - started) * 1000)
        return CheckResult(
            check_id,
            State.BLOCKED,
            f"명령을 실행할 수 없습니다: {error}",
            normalized_command,
            None,
            duration_ms,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    output = _last_output(result.stdout, result.stderr)
    state = State.PASS if result.returncode == 0 else State.BLOCKED
    reason = output or (
        "환경 명령이 성공했습니다."
        if state is State.PASS
        else "환경 명령이 실패했습니다."
    )
    return CheckResult(
        check_id,
        state,
        reason,
        normalized_command,
        result.returncode,
        duration_ms,
    )


def run_prepare_preflight(root: Path) -> tuple[CheckResult, ...]:
    checks: list[CheckResult] = []
    version = sys.version_info
    python_state = State.PASS if version >= (3, 13) else State.BLOCKED
    checks.append(
        CheckResult(
            "environment.python",
            python_state,
            f"Python {version.major}.{version.minor}.{version.micro}",
        )
    )

    if shutil.which("java") is None:
        checks.append(
            CheckResult(
                "environment.java",
                State.BLOCKED,
                "java binary를 찾을 수 없습니다.",
                ("java", "-version"),
            )
        )
    else:
        checks.append(
            blocked_environment_check(
                root,
                "environment.java",
                ("java", "-version"),
            )
        )

    if shutil.which("docker") is None:
        checks.append(
            CheckResult(
                "environment.docker",
                State.BLOCKED,
                "docker binary를 찾을 수 없습니다.",
                ("docker", "info"),
            )
        )
    else:
        checks.append(
            blocked_environment_check(
                root,
                "environment.docker",
                ("docker", "info"),
            )
        )

    gradlew = root / "gradlew"
    gradle_command = ("./gradlew", "-q", "javaToolchains")
    if not gradlew.is_file() or not os.access(gradlew, os.X_OK):
        checks.append(
            CheckResult(
                "environment.java17-toolchain",
                State.BLOCKED,
                "실행 가능한 ./gradlew를 찾을 수 없습니다.",
                gradle_command,
            )
        )
    else:
        toolchain_check = blocked_environment_check(
            root,
            "environment.java17-toolchain",
            gradle_command,
        )
        if (
            toolchain_check.state is State.PASS
            and re.search(r"Language Version:\s*17\b", toolchain_check.reason) is None
        ):
            toolchain_check = CheckResult(
                toolchain_check.check_id,
                State.BLOCKED,
                f"Java 17 toolchain을 확인할 수 없습니다: {toolchain_check.reason}",
                toolchain_check.command,
                toolchain_check.exit_code,
                toolchain_check.duration_ms,
            )
        checks.append(toolchain_check)

    return tuple(checks)


def validate_preflight_results(raw_checks: Sequence[CheckResult]) -> tuple[CheckResult, ...]:
    try:
        checks = tuple(raw_checks)
    except (TypeError, ValueError) as error:
        raise _violation(
            State.FAIL,
            "environment.preflight",
            f"preflight 결과를 해석할 수 없습니다: {error}",
        ) from error

    check_ids: list[str] = []
    for check in checks:
        schema_error = _check_result_schema_error(check, "preflight")
        if schema_error is not None:
            raise _violation(
                State.FAIL,
                "environment.preflight",
                schema_error,
            )
        check_ids.append(check.check_id)

    actual_ids = set(check_ids)
    if len(check_ids) != len(actual_ids):
        raise _violation(
            State.FAIL,
            "environment.preflight",
            "preflight check_id가 중복되었습니다.",
        )
    if actual_ids != REQUIRED_PREFLIGHT_CHECK_IDS:
        raise _violation(
            State.FAIL,
            "environment.preflight",
            "preflight check_id 집합이 정확하지 않습니다: "
            f"actual={sorted(actual_ids)}, "
            f"required={sorted(REQUIRED_PREFLIGHT_CHECK_IDS)}",
        )
    return checks


def execute_command(
    root: Path,
    check_id: str,
    command: Sequence[str],
) -> CheckResult:
    normalized_command = tuple(command)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    started = time.monotonic()
    try:
        result = subprocess.run(
            normalized_command,
            cwd=root,
            check=False,
            capture_output=True,
            env=environment,
            shell=False,
        )
    except OSError as error:
        duration_ms = int((time.monotonic() - started) * 1000)
        return CheckResult(
            check_id,
            State.FAIL,
            f"명령을 실행할 수 없습니다: {error}",
            normalized_command,
            None,
            duration_ms,
        )

    duration_ms = int((time.monotonic() - started) * 1000)
    full_output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    output = full_output[-4000:].strip()
    if result.returncode == 0:
        state = State.PASS
    elif (
        (check_id == "gradle.test" or check_id.startswith("oracle."))
        and "Could not find a valid Docker environment" in full_output
    ):
        state = State.BLOCKED
    else:
        state = State.FAIL
    return CheckResult(
        check_id,
        state,
        output or "출력 없음",
        normalized_command,
        result.returncode,
        duration_ms,
    )


def required_check_ids(
    plan: Plan,
    classification: RiskClassification,
    policy: RiskPolicy,
) -> tuple[str, ...]:
    selected = {"harness.unit", "gradle.test"}
    for risk in set(plan.declared_risks).union(classification.detected_risks):
        selected.update(policy.risk_checks[risk])
    selected.difference_update(INLINE_CHECK_IDS)
    selected.difference_update({"harness.unit", "gradle.test"})
    return ("harness.unit", "gradle.test", *sorted(selected))


def run_required_checks(
    root: Path,
    check_ids: Sequence[str],
) -> tuple[CheckResult, ...]:
    checks: list[CheckResult] = []
    for check_id in check_ids:
        if check_id == "harness.unit":
            checks.append(execute_command(root, check_id, HARNESS_TEST_COMMAND))
        elif check_id == "gradle.test":
            environment_checks = validate_preflight_results(
                run_prepare_preflight(root)
            )
            checks.extend(environment_checks)
            if all(check.state is State.PASS for check in environment_checks):
                checks.append(execute_command(root, check_id, GRADLE_TEST_COMMAND))
            else:
                blocked_ids = [
                    check.check_id
                    for check in environment_checks
                    if check.state is not State.PASS
                ]
                checks.append(
                    CheckResult(
                        check_id,
                        State.BLOCKED,
                        f"필수 환경 검사가 통과하지 않았습니다: {blocked_ids}",
                        GRADLE_TEST_COMMAND,
                    )
                )
        elif check_id in DOMAIN_ORACLE_CHECK_IDS:
            checks.append(
                execute_command(
                    root,
                    check_id,
                    (
                        sys.executable,
                        ORACLE_SCRIPT_PATH,
                        root.as_posix(),
                        check_id,
                    ),
                )
            )
        else:
            checks.append(
                CheckResult(
                    check_id,
                    State.BLOCKED,
                    "구현되지 않은 필수 check입니다.",
                )
            )
    return tuple(checks)


def _check_result_schema_error(check: object, source_label: str) -> str | None:
    if not isinstance(check, CheckResult):
        return f"{source_label} 결과는 CheckResult여야 합니다."
    if (
        not isinstance(check.check_id, str)
        or not check.check_id
        or check.check_id != check.check_id.strip()
        or any(unicodedata.category(character) == "Cc" for character in check.check_id)
    ):
        return f"{source_label} check_id가 올바르지 않습니다."
    if not isinstance(check.state, State):
        return f"{source_label} state가 올바르지 않습니다: {check.check_id}"
    if not isinstance(check.reason, str):
        return f"{source_label} reason이 문자열이 아닙니다: {check.check_id}"
    if not isinstance(check.command, tuple) or any(
        not isinstance(argument, str) for argument in check.command
    ):
        return f"{source_label} command가 문자열 tuple이 아닙니다: {check.check_id}"
    if check.exit_code is not None and type(check.exit_code) is not int:
        return f"{source_label} exit_code가 올바르지 않습니다: {check.check_id}"
    if check.duration_ms is not None and (
        type(check.duration_ms) is not int or check.duration_ms < 0
    ):
        return f"{source_label} duration_ms가 올바르지 않습니다: {check.check_id}"
    return None


def validate_check_runner_results(
    raw_checks: object,
    requested_ids: Sequence[str],
) -> tuple[tuple[CheckResult, ...], CheckResult | None]:
    try:
        candidates = tuple(raw_checks)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        return (), CheckResult(
            "checks.runner",
            State.FAIL,
            f"check runner 결과를 해석할 수 없습니다: {error}",
        )

    valid_checks: list[CheckResult] = []
    for candidate in candidates:
        schema_error = _check_result_schema_error(candidate, "check runner")
        if schema_error is not None:
            return tuple(valid_checks), CheckResult(
                "checks.runner",
                State.FAIL,
                schema_error,
            )
        valid_checks.append(candidate)

    check_ids = [check.check_id for check in valid_checks]
    duplicate_ids = sorted(
        {check_id for check_id in check_ids if check_ids.count(check_id) > 1}
    )
    if duplicate_ids:
        return tuple(valid_checks), CheckResult(
            "checks.runner",
            State.FAIL,
            f"check runner check_id가 중복되었습니다: {duplicate_ids}",
        )

    requested = tuple(requested_ids)
    required_ids = set(requested)
    if "gradle.test" in requested:
        required_ids.update(REQUIRED_PREFLIGHT_CHECK_IDS)
    missing = sorted(required_ids - set(check_ids))
    if missing:
        return tuple(valid_checks), CheckResult(
            "checks.runner",
            State.FAIL,
            f"필수 check 결과가 누락되었습니다: {missing}",
        )

    allowed_extras = (
        REQUIRED_PREFLIGHT_CHECK_IDS if "gradle.test" in requested else frozenset()
    )
    unknown_extras = sorted(set(check_ids) - set(requested) - set(allowed_extras))
    if unknown_extras:
        return tuple(valid_checks), CheckResult(
            "checks.runner",
            State.FAIL,
            f"허용되지 않은 추가 check 결과가 있습니다: {unknown_extras}",
        )
    return tuple(valid_checks), None


def validate_prepare_clean_state(root: Path, plan: Plan) -> None:
    dirty_paths = collect_worktree_paths(root)
    unexpected_paths = [path for path in dirty_paths if path != plan.relative_path]
    if unexpected_paths:
        rendered_paths = ", ".join(repr(path) for path in unexpected_paths)
        raise _violation(
            State.REPLAN_REQUIRED,
            "git.clean",
            f"선택한 plan 외 변경이 있습니다: {rendered_paths}",
        )


def validate_evaluate_clean_state(root: Path, phase: str) -> None:
    dirty_paths = collect_worktree_paths(root)
    if dirty_paths:
        rendered_paths = ", ".join(repr(path) for path in dirty_paths)
        raise _violation(
            State.REPLAN_REQUIRED,
            "git.clean",
            f"evaluate {phase} worktree가 clean하지 않습니다: {rendered_paths}",
        )


def prepare(
    root: Path,
    plan_path: Path,
    preflight: Callable[[Path], Sequence[CheckResult]] = run_prepare_preflight,
) -> tuple[State, tuple[CheckResult, ...]]:
    try:
        resolved_root = _strict_repository_root(root)
        lock_path = remove_stale_plan_lock(resolved_root)

        policy = load_risk_policy(resolved_root / "harness" / "risk-policy.json")
        plan = load_plan(resolved_root, plan_path, policy)
        context = resolve_local_git_context(resolved_root, plan)
        initial_snapshot = make_plan_lock(plan, context)
        validate_prepare_clean_state(resolved_root, plan)

        environment_checks = validate_preflight_results(preflight(resolved_root))
        for check in environment_checks:
            if check.state is not State.PASS:
                return check.state, environment_checks

        current_policy = load_risk_policy(
            resolved_root / "harness" / "risk-policy.json"
        )
        current_plan = load_plan(resolved_root, plan_path, current_policy)
        current_context = resolve_local_git_context(resolved_root, current_plan)
        validate_prepare_clean_state(resolved_root, current_plan)
        validate_plan_lock(initial_snapshot, current_plan, current_context)

        lock_path = safe_evidence_lock_path(resolved_root)
        lock = make_plan_lock(current_plan, current_context)
        write_json_atomic(lock_path, plan_lock_payload(lock))
        prepare_check = CheckResult(
            "prepare",
            State.PASS,
            "plan, branch, base tip, merge-base를 잠갔습니다.",
        )
        return State.PASS, (*environment_checks, prepare_check)
    except HarnessViolation as error:
        return error.state, (CheckResult(error.check_id, error.state, error.reason),)
    except Exception as error:
        return State.FAIL, (
            CheckResult(
                "harness.internal",
                State.FAIL,
                f"{type(error).__name__}: {error}",
            ),
        )


def _freshness_check(
    root: Path,
    plan_path: Path,
    initial_plan: Plan,
    initial_context: GitContext,
    initial_changed_paths: tuple[str, ...],
    initial_diff_hash: str,
) -> tuple[CheckResult, Plan | None, GitContext | None]:
    try:
        validate_evaluate_clean_state(root, "종료")
        current_policy = load_risk_policy(root / "harness" / "risk-policy.json")
        current_plan = load_plan(root, plan_path, current_policy)
        current_context = resolve_local_git_context(root, current_plan)
        current_changed_paths = collect_local_changed_paths(
            root,
            current_context.merge_base_sha,
        )
        current_diff_hash = compute_diff_hash(
            root,
            current_context,
            current_changed_paths,
        )
    except HarnessViolation as error:
        if error.check_id == "git.clean":
            return (
                CheckResult(error.check_id, error.state, error.reason),
                None,
                None,
            )
        plan_identity_checks = {
            "plan.path",
            "plan.schema",
            "plan.scope",
            "plan.contract-changes",
            "git.branch",
        }
        state = (
            State.REPLAN_REQUIRED
            if error.check_id in plan_identity_checks
            or error.state is State.REPLAN_REQUIRED
            else error.state
        )
        return (
            CheckResult(
                "evidence.freshness",
                state,
                f"종료 identity를 확인할 수 없습니다: {error.check_id}: {error.reason}",
            ),
            None,
            None,
        )
    except Exception as error:
        return (
            CheckResult(
                "evidence.freshness",
                State.FAIL,
                f"종료 identity 확인 중 오류가 발생했습니다: {type(error).__name__}: {error}",
            ),
            None,
            None,
        )

    comparisons = (
        ("base tip", initial_context.base_tip_sha, current_context.base_tip_sha),
        ("merge-base", initial_context.merge_base_sha, current_context.merge_base_sha),
        ("HEAD", initial_context.candidate_head_sha, current_context.candidate_head_sha),
        ("tested revision", initial_context.tested_revision_sha, current_context.tested_revision_sha),
        ("plan path", initial_plan.relative_path, current_plan.relative_path),
        ("plan hash", initial_plan.plan_hash, current_plan.plan_hash),
        ("changed paths", initial_changed_paths, current_changed_paths),
        ("diff hash", initial_diff_hash, current_diff_hash),
    )
    changed = [label for label, before, after in comparisons if before != after]
    if changed:
        return (
            CheckResult(
                "evidence.freshness",
                State.REPLAN_REQUIRED,
                f"검사 중 identity가 변경되었습니다: {', '.join(changed)}",
            ),
            current_plan,
            current_context,
        )
    return (
        CheckResult(
            "evidence.freshness",
            State.PASS,
            "worktree가 clean하고 plan, base tip, merge-base, HEAD, paths, diff hash가 유지되었습니다.",
        ),
        current_plan,
        current_context,
    )


def _evaluation_from_values(
    *,
    checks: Sequence[CheckResult],
    plan_path: str,
    plan: Plan | None,
    context: GitContext | None,
    classification: RiskClassification | None,
    changed_paths: tuple[str, ...],
    diff_hash: str | None,
) -> Evaluation:
    normalized_checks = tuple(checks)
    return Evaluation(
        schema_version=1,
        state=aggregate_state(normalized_checks),
        base_tip_sha=context.base_tip_sha if context is not None else None,
        merge_base_sha=context.merge_base_sha if context is not None else None,
        candidate_head_sha=(
            context.candidate_head_sha if context is not None else None
        ),
        tested_revision_sha=(
            context.tested_revision_sha if context is not None else None
        ),
        plan_path=plan.relative_path if plan is not None else plan_path,
        plan_hash=plan.plan_hash if plan is not None else None,
        declared_risks=plan.declared_risks if plan is not None else (),
        detected_risks=(
            classification.detected_risks if classification is not None else ()
        ),
        changed_paths=changed_paths,
        diff_hash=diff_hash,
        checks=normalized_checks,
    )


def evaluate(
    root: Path,
    plan_path: Path,
    check_runner: Callable[[Path, Sequence[str]], object] = run_required_checks,
) -> Evaluation:
    requested_plan_path = plan_path.as_posix()
    checks: list[CheckResult] = []
    plan: Plan | None = None
    context: GitContext | None = None
    lock: PlanLock | None = None
    classification: RiskClassification | None = None
    changed_paths: tuple[str, ...] = ()
    diff_hash: str | None = None
    evaluation_path: Path | None = None
    ending_plan: Plan | None = None
    ending_context: GitContext | None = None

    try:
        resolved_root = _strict_repository_root(root)
        evaluation_path = remove_stale_evaluation(resolved_root)
    except HarnessViolation as error:
        checks.append(CheckResult(error.check_id, error.state, error.reason))
        return _evaluation_from_values(
            checks=checks,
            plan_path=requested_plan_path,
            plan=None,
            context=None,
            classification=None,
            changed_paths=(),
            diff_hash=None,
        )
    except Exception as error:
        checks.append(
            CheckResult(
                "harness.internal",
                State.FAIL,
                f"{type(error).__name__}: {error}",
            )
        )
        return _evaluation_from_values(
            checks=checks,
            plan_path=requested_plan_path,
            plan=None,
            context=None,
            classification=None,
            changed_paths=(),
            diff_hash=None,
        )

    try:
        validate_evaluate_clean_state(resolved_root, "시작")
        policy = load_risk_policy(resolved_root / "harness" / "risk-policy.json")
        plan = load_plan(resolved_root, plan_path, policy)
        context = resolve_local_git_context(resolved_root, plan)
        lock = load_plan_lock(safe_evidence_lock_path(resolved_root))
        validate_plan_lock(lock, plan, context)
        checks.append(
            CheckResult(
                "plan.lock",
                State.PASS,
                "prepare 시점의 plan, branch, base tip, merge-base와 일치합니다.",
            )
        )

        changed_paths = collect_local_changed_paths(
            resolved_root,
            context.merge_base_sha,
        )
        diff_hash = compute_diff_hash(resolved_root, context, changed_paths)

        validate_existing_migrations_immutable(
            resolved_root,
            context,
            changed_paths,
        )
        checks.append(
            CheckResult(
                "migration.immutable",
                State.PASS,
                "기존 Flyway migration 변경이 없습니다.",
            )
        )

        outside_paths = scope_violations(changed_paths, plan)
        if outside_paths:
            raise _violation(
                State.REPLAN_REQUIRED,
                "scope.allowed-paths",
                f"allowedPaths 밖 변경이 있습니다: {list(outside_paths)}",
            )
        checks.append(
            CheckResult(
                "scope.allowed-paths",
                State.PASS,
                "모든 변경 경로가 plan 범위 안에 있습니다.",
            )
        )

        classification = classify_risks(
            changed_paths,
            policy,
            plan.relative_path,
        )
        if classification.unclassified_paths:
            raise _violation(
                State.REPLAN_REQUIRED,
                "risk.classification",
                f"미분류 경로가 있습니다: {list(classification.unclassified_paths)}",
            )
        checks.append(
            CheckResult(
                "risk.classification",
                State.PASS,
                "모든 변경 경로가 위험 정책으로 분류되었습니다.",
            )
        )

        validate_risk_declarations(plan, classification)
        checks.append(
            CheckResult(
                "risk.declaration",
                State.PASS,
                "감지된 위험이 plan에 선언되었습니다.",
            )
        )

        validate_contract_changes(changed_paths, plan, policy)
        checks.append(
            CheckResult(
                "trust-root.contract",
                State.PASS,
                "보호 경로 변경이 정확한 contractChanges로 선언되었습니다.",
            )
        )

        requested_ids = required_check_ids(plan, classification, policy)
        raw_runner_results = check_runner(resolved_root, requested_ids)
        runner_results, runner_error = validate_check_runner_results(
            raw_runner_results,
            requested_ids,
        )
        checks.extend(runner_results)
        if runner_error is not None:
            checks.append(runner_error)
    except HarnessViolation as error:
        checks.append(CheckResult(error.check_id, error.state, error.reason))
    except Exception as error:
        checks.append(
            CheckResult(
                "harness.internal",
                State.FAIL,
                f"{type(error).__name__}: {error}",
            )
        )

    if plan is not None and context is not None and diff_hash is not None:
        freshness, ending_plan, ending_context = _freshness_check(
            resolved_root,
            plan_path,
            plan,
            context,
            changed_paths,
            diff_hash,
        )
        checks.append(freshness)

    can_write = evaluation_path is not None
    lock_restore_path: Path | None = None
    if lock is not None:
        if ending_plan is None or ending_context is None:
            checks.append(
                CheckResult(
                    "plan.lock.restore",
                    State.BLOCKED,
                    "종료 plan/context를 검증하지 못해 plan lock을 복구하지 않습니다.",
                )
            )
        else:
            try:
                validate_plan_lock(lock, ending_plan, ending_context)
            except HarnessViolation as error:
                checks.append(
                    CheckResult(
                        "plan.lock.restore",
                        error.state,
                        f"stale plan lock을 복구하지 않습니다: {error.reason}",
                    )
                )
            else:
                lock_restore_path = resolved_root / "build" / "harness" / "plan.lock.json"

    try:
        final_evaluation_path = safe_evidence_evaluation_path(resolved_root)
        if evaluation_path is not None and final_evaluation_path != evaluation_path:
            raise _evidence_path_error("evaluation path가 검사 중 변경되었습니다.")
        evaluation_path = final_evaluation_path
        if lock_restore_path is not None:
            final_lock_path = safe_evidence_lock_path(resolved_root)
            if final_lock_path != lock_restore_path:
                raise _evidence_path_error("plan lock path가 검사 중 변경되었습니다.")
            lock_restore_path = final_lock_path
    except HarnessViolation as error:
        checks.append(CheckResult(error.check_id, error.state, error.reason))
        can_write = False
    except Exception as error:
        checks.append(
            CheckResult(
                "evidence.path",
                State.FAIL,
                f"evaluation path 재검사 중 오류가 발생했습니다: {type(error).__name__}: {error}",
            )
        )
        can_write = False

    evaluation = _evaluation_from_values(
        checks=checks,
        plan_path=requested_plan_path,
        plan=plan,
        context=context,
        classification=classification,
        changed_paths=changed_paths,
        diff_hash=diff_hash,
    )
    if can_write and evaluation_path is not None:
        try:
            if lock is not None and lock_restore_path is not None:
                write_json_atomic(lock_restore_path, plan_lock_payload(lock))
            write_json_atomic(evaluation_path, evaluation.to_dict())
        except Exception as error:
            checks.append(
                CheckResult(
                    "evidence.write",
                    State.FAIL,
                    f"evaluation을 기록할 수 없습니다: {type(error).__name__}: {error}",
                )
            )
            evaluation = _evaluation_from_values(
                checks=checks,
                plan_path=requested_plan_path,
                plan=plan,
                context=context,
                classification=classification,
                changed_paths=changed_paths,
                diff_hash=diff_hash,
            )
    return evaluation


class CliParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _violation(State.FAIL, "cli.arguments", message)


def build_parser() -> argparse.ArgumentParser:
    parser = CliParser(prog="agent-harness.py")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("plan", type=Path)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("plan", type=Path)
    return parser


def print_checks(checks: Sequence[CheckResult]) -> None:
    for check in checks:
        print(f"[{check.state.name}] {check.check_id}: {check.reason!r}")


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = build_parser().parse_args(argv)
        root = find_git_root(Path.cwd())
        if arguments.command == "prepare":
            state, checks = prepare(root, arguments.plan)
            print_checks(checks)
            return int(state)
        if arguments.command == "evaluate":
            evaluation = evaluate(root, arguments.plan)
            print_checks(evaluation.checks)
            return int(evaluation.state)
        raise _violation(State.FAIL, "cli.arguments", "지원하지 않는 command입니다.")
    except HarnessViolation as error:
        print(
            f"[{error.state.name}] {error.check_id}: {error.reason!r}",
            file=sys.stderr,
        )
        return int(error.state)
    except Exception as error:
        reason = f"{type(error).__name__}: {error}"
        print(f"[FAIL] harness.internal: {reason!r}", file=sys.stderr)
        return int(State.FAIL)


if __name__ == "__main__":
    raise SystemExit(main())
