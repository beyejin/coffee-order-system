from __future__ import annotations

import hashlib
import importlib.util
import inspect
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "agent-harness.py"
SPEC = importlib.util.spec_from_file_location("agent_harness", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load agent harness: {SCRIPT}")
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)

SOURCE_POLICY = REPO_ROOT / "harness" / "risk-policy.json"
KNOWN_RISKS = frozenset({"transaction", "concurrency"})


def valid_plan_bytes(issue: int = 123) -> bytes:
    payload = {
        "issue": issue,
        "targetBranch": "main",
        "objective": "충전과 주문의 통합 동시성 검증",
        "allowedPaths": [
            "src/test/java/com/example/coffee/concurrency/"
            "CrossDomainConcurrencyIntegrationTest.java",
            "docs/logs/concurrency-test.md",
        ],
        "acceptanceCriteria": [
            "최종 잔액과 성공 이력 합계가 일치한다.",
        ],
        "declaredRisks": ["transaction", "concurrency"],
        "contractChanges": [],
        "nonGoals": ["운영 코드 변경", "락 전략 변경"],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def fixture_plan_bytes(issue: int) -> bytes:
    payload = {
        "issue": issue,
        "targetBranch": "main",
        "objective": "임시 저장소의 하네스 판정 검증",
        "allowedPaths": ["AGENTS.md"],
        "acceptanceCriteria": ["현재 diff만 판정한다."],
        "declaredRisks": ["completion"],
        "contractChanges": [],
        "nonGoals": ["제품 코드 변경"],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ("git", *args),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


REQUIRED_PREFLIGHT_IDS = (
    "environment.python",
    "environment.java",
    "environment.docker",
    "environment.java17-toolchain",
)


def fixture_preflight(
    root: Path,
    docker_state: object,
) -> tuple[object, ...]:
    return tuple(
        HARNESS.CheckResult(
            check_id,
            docker_state if check_id == "environment.docker" else HARNESS.State.PASS,
            str(root),
        )
        for check_id in REQUIRED_PREFLIGHT_IDS
    )


def passing_preflight(root: Path) -> tuple[object, ...]:
    return fixture_preflight(root, HARNESS.State.PASS)


def passing_required_checks(
    _root: Path,
    check_ids: tuple[str, ...],
) -> tuple[object, ...]:
    checks: list[object] = []
    for check_id in check_ids:
        if check_id == "gradle.test":
            checks.extend(
                HARNESS.CheckResult(
                    preflight_id,
                    HARNESS.State.PASS,
                    "fixture pass",
                )
                for preflight_id in REQUIRED_PREFLIGHT_IDS
            )
        checks.append(
            HARNESS.CheckResult(check_id, HARNESS.State.PASS, "fixture pass")
        )
    return tuple(checks)


def make_plan(
    allowed_paths: tuple[str, ...] = ("AGENTS.md",),
    declared_risks: tuple[str, ...] = ("completion",),
    contract_changes: tuple[str, ...] = (),
) -> object:
    return HARNESS.Plan(
        issue=123,
        target_branch="main",
        objective="임시 저장소의 하네스 판정 검증",
        allowed_paths=allowed_paths,
        acceptance_criteria=("현재 diff만 판정한다.",),
        declared_risks=declared_risks,
        contract_changes=contract_changes,
        non_goals=("제품 코드 변경",),
        relative_path="harness/plans/123.json",
        plan_hash="0" * 64,
    )


def make_policy(rules: tuple[object, ...] | None = None) -> object:
    known_risks = frozenset(
        {
            "scope",
            "architecture",
            "api",
            "migration",
            "transaction",
            "concurrency",
            "async",
            "multi-instance",
            "completion",
        }
    )
    if rules is None:
        rules = (
            HARNESS.RiskRule(
                rule_id="agent-router",
                patterns=("AGENTS.md",),
                risks=("completion",),
            ),
        )
    return HARNESS.RiskPolicy(
        schema_version=1,
        known_risks=known_risks,
        rules=rules,
        protected_patterns=("scripts/agent-harness.py",),
        risk_checks={risk: (f"dummy.{risk}",) for risk in known_risks},
        implemented_checks=frozenset(),
    )


class GitFixture:
    def __init__(self, issue: int = 123) -> None:
        self.issue = issue
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.base = Path(self._temporary_directory.name)
        self.origin = self.base / "origin.git"
        self.work = self.base / "work"

        git(self.base, "init", "--bare", "origin.git")
        git(self.base, "clone", str(self.origin), str(self.work))
        git(self.work, "config", "user.name", "Harness Test")
        git(self.work, "config", "user.email", "harness@example.com")

        (self.work / "harness" / "plans").mkdir(parents=True)
        (self.work / "src" / "main" / "resources" / "db" / "migration").mkdir(
            parents=True
        )
        (self.work / "harness" / "risk-policy.json").write_bytes(
            SOURCE_POLICY.read_bytes()
        )
        (self.work / self.plan()).write_bytes(fixture_plan_bytes(issue))
        (
            self.work
            / "src"
            / "main"
            / "resources"
            / "db"
            / "migration"
            / "V1__fixture.sql"
        ).write_text("create table fixture(id bigint);\n", encoding="utf-8")
        (self.work / "AGENTS.md").write_text("# fixture\n", encoding="utf-8")
        (self.work / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.work / "tracked.txt").write_text("base\n", encoding="utf-8")
        (self.work / "rename-old.txt").write_text("rename\n", encoding="utf-8")

        git(self.work, "add", ".")
        git(self.work, "commit", "-m", "fixture base")
        git(self.work, "branch", "-M", "main")
        git(self.work, "push", "-u", "origin", "main")
        git(self.origin, "symbolic-ref", "HEAD", "refs/heads/main")
        git(
            self.work,
            "checkout",
            "-b",
            f"feature/{issue}-agent-harness-core",
        )

    def close(self) -> None:
        self._temporary_directory.cleanup()

    def policy(self) -> object:
        return HARNESS.load_risk_policy(self.work / "harness" / "risk-policy.json")

    def plan(self) -> Path:
        return Path(f"harness/plans/{self.issue}.json")

    def advance_origin_main_without_merging(self) -> None:
        other = self.base / "other"
        git(self.base, "clone", str(self.origin), str(other))
        git(other, "config", "user.name", "Harness Test")
        git(other, "config", "user.email", "harness@example.com")
        (other / "main.txt").write_text("advanced\n", encoding="utf-8")
        git(other, "add", "main.txt")
        git(other, "commit", "-m", "advance main")
        git(other, "push", "origin", "main")

    def create_all_change_kinds(self) -> None:
        (self.work / "committed.txt").write_text("committed\n", encoding="utf-8")
        git(self.work, "mv", "rename-old.txt", "rename-new.txt")
        git(self.work, "add", "committed.txt")
        git(self.work, "commit", "-m", "candidate commit")
        (self.work / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(self.work, "add", "staged.txt")
        (self.work / "tracked.txt").write_text("unstaged\n", encoding="utf-8")
        (self.work / "untracked.txt").write_text("untracked\n", encoding="utf-8")

    def context(self, merge_base_sha: str | None = None) -> object:
        base_tip_sha = git(self.work, "rev-parse", "origin/main")
        candidate_head_sha = git(self.work, "rev-parse", "HEAD")
        return HARNESS.GitContext(
            branch=f"feature/{self.issue}-agent-harness-core",
            target_branch="main",
            base_tip_sha=base_tip_sha,
            merge_base_sha=merge_base_sha or base_tip_sha,
            candidate_head_sha=candidate_head_sha,
            tested_revision_sha=candidate_head_sha,
        )

    def prepare_and_add_outside_path(self) -> None:
        state, _checks = HARNESS.prepare(
            self.work,
            self.plan(),
            preflight=passing_preflight,
        )
        if state is not HARNESS.State.PASS:
            raise AssertionError(f"fixture prepare failed: {state}")
        (self.work / "outside.md").write_text("outside\n", encoding="utf-8")

    def prepare_scope_only_change(self) -> None:
        state, _checks = HARNESS.prepare(
            self.work,
            self.plan(),
            preflight=passing_preflight,
        )
        if state is not HARNESS.State.PASS:
            raise AssertionError(f"fixture prepare failed: {state}")
        (self.work / "AGENTS.md").write_text("# changed\n", encoding="utf-8")


class StateAndPlanTest(unittest.TestCase):
    def test_state_values_equal_cli_exit_codes(self) -> None:
        self.assertEqual(0, HARNESS.State.PASS)
        self.assertEqual(1, HARNESS.State.FAIL)
        self.assertEqual(2, HARNESS.State.BLOCKED)
        self.assertEqual(3, HARNESS.State.REPLAN_REQUIRED)

    def test_parse_plan_accepts_exact_schema(self) -> None:
        raw = valid_plan_bytes()
        plan = HARNESS.parse_plan(
            raw,
            "harness/plans/123.json",
            KNOWN_RISKS,
        )

        self.assertEqual(123, plan.issue)
        self.assertEqual("main", plan.target_branch)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), plan.plan_hash)

    def test_parse_plan_rejects_duplicate_top_level_key(self) -> None:
        raw = valid_plan_bytes().replace(
            b'"issue": 123',
            b'"issue": 123, "issue": 123',
            1,
        )

        with self.assertRaisesRegex(HARNESS.HarnessViolation, "중복 key") as raised:
            HARNESS.parse_plan(raw, "harness/plans/123.json", KNOWN_RISKS)

        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("plan.schema", raised.exception.check_id)

    def test_parse_plan_rejects_unknown_field(self) -> None:
        payload = json.loads(valid_plan_bytes())
        payload["baseSha"] = "deadbeef"

        with self.assertRaisesRegex(HARNESS.HarnessViolation, "미지원 필드"):
            HARNESS.parse_plan(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "harness/plans/123.json",
                KNOWN_RISKS,
            )

    def test_parse_plan_rejects_boolean_issue(self) -> None:
        with self.assertRaises(HARNESS.HarnessViolation):
            HARNESS.parse_plan(
                valid_plan_bytes(issue=True),
                "harness/plans/123.json",
                KNOWN_RISKS,
            )

    def test_parse_plan_rejects_malformed_contract_changes(self) -> None:
        for declaration in (
            "not scripts/agent-harness.py changed",
            "scripts/agent-harness.py",
            ". v1",
            "docs/./api.md v1",
            "docs/api.md/ v1",
            "docs/\x00api.md v1",
        ):
            with self.subTest(declaration=declaration):
                payload = json.loads(valid_plan_bytes())
                payload["contractChanges"] = [declaration]

                with self.assertRaisesRegex(
                    HARNESS.HarnessViolation,
                    "contractChanges",
                ) as raised:
                    HARNESS.parse_plan(
                        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "harness/plans/123.json",
                        KNOWN_RISKS,
                    )

                self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)

    def test_parse_plan_rejects_whitespace_normalization(self) -> None:
        payloads: list[tuple[str, dict[str, object]]] = []

        target_branch = json.loads(valid_plan_bytes())
        target_branch["targetBranch"] = " main "
        payloads.append(("targetBranch", target_branch))

        leading_nbsp_path = json.loads(valid_plan_bytes())
        leading_nbsp_path["allowedPaths"][0] = "\u00a0docs/logs/order.md"
        payloads.append(("leading NBSP path", leading_nbsp_path))

        trailing_newline_path = json.loads(valid_plan_bytes())
        trailing_newline_path["allowedPaths"][0] = "docs/logs/order.md\n"
        payloads.append(("trailing newline path", trailing_newline_path))

        whitespace_risk = json.loads(valid_plan_bytes())
        whitespace_risk["declaredRisks"][0] = "transaction "
        payloads.append(("declared risk", whitespace_risk))

        for label, payload in payloads:
            with self.subTest(label=label):
                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.parse_plan(
                        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "harness/plans/123.json",
                        KNOWN_RISKS,
                    )

                self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
                self.assertEqual("plan.schema", raised.exception.check_id)

    def test_parse_plan_rejects_noncanonical_repository_paths(self) -> None:
        for pattern in (
            ".",
            "docs/./x.md",
            "docs/x.md/",
            "docs/\x00x.md",
            "docs/\x1fx.md",
            "docs/\x7fx.md",
            "docs/\u0080x.md",
            "docs/\u009fx.md",
        ):
            with self.subTest(pattern=repr(pattern)):
                payload = json.loads(valid_plan_bytes())
                payload["allowedPaths"] = [pattern]

                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.parse_plan(
                        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        "harness/plans/123.json",
                        KNOWN_RISKS,
                    )

                self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
                self.assertEqual("plan.schema", raised.exception.check_id)

    def test_plan_path_must_match_issue_number(self) -> None:
        with self.assertRaisesRegex(HARNESS.HarnessViolation, "plan 경로"):
            HARNESS.parse_plan(
                valid_plan_bytes(),
                "harness/plans/124.json",
                KNOWN_RISKS,
            )

    def test_broad_src_glob_requires_replan(self) -> None:
        payload = json.loads(valid_plan_bytes())
        payload["allowedPaths"] = ["src/**"]

        with self.assertRaisesRegex(HARNESS.HarnessViolation, "광범위") as raised:
            HARNESS.parse_plan(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                "harness/plans/123.json",
                KNOWN_RISKS,
            )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)

    def test_path_match_does_not_accept_sibling_prefix(self) -> None:
        self.assertTrue(HARNESS.path_matches("docs/logs/**", "docs/logs/order.md"))
        self.assertFalse(
            HARNESS.path_matches("docs/logs/**", "docs/logstash/order.md")
        )

    def test_load_plan_reads_plan_inside_repository_root(self) -> None:
        policy = HARNESS.load_risk_policy(SOURCE_POLICY)
        raw = valid_plan_bytes()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            plan_path = root / "harness" / "plans" / "123.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(raw)

            plan = HARNESS.load_plan(
                root,
                Path("harness/plans/123.json"),
                policy,
            )

        self.assertEqual(123, plan.issue)
        self.assertEqual("harness/plans/123.json", plan.relative_path)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), plan.plan_hash)

    def test_load_plan_rejects_symlink_outside_repository_root(self) -> None:
        policy = HARNESS.load_risk_policy(SOURCE_POLICY)

        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            root = temp / "repo"
            plan_path = root / "harness" / "plans" / "123.json"
            plan_path.parent.mkdir(parents=True)
            outside_plan = temp / "outside.json"
            outside_plan.write_bytes(valid_plan_bytes())
            plan_path.symlink_to(outside_plan)

            with self.assertRaises(HARNESS.HarnessViolation) as raised:
                HARNESS.load_plan(
                    root,
                    Path("harness/plans/123.json"),
                    policy,
                )

        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("plan.path", raised.exception.check_id)

    def test_policy_rejects_unknown_field(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["allowUnknown"] = True

        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(HARNESS.HarnessViolation, "최상위 필드"):
                HARNESS.load_risk_policy(policy_path)

    def test_policy_rejects_duplicate_nested_key(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).replace(
            '"riskChecks":{',
            '"riskChecks":{"scope":["scope.injected"],',
            1,
        )

        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(raw, encoding="utf-8")

            with self.assertRaisesRegex(
                HARNESS.HarnessViolation,
                "중복 key",
            ) as raised:
                HARNESS.load_risk_policy(policy_path)

        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("policy.schema", raised.exception.check_id)

    def test_policy_rejects_whitespace_normalization(self) -> None:
        for label in ("rule id", "path", "risk", "check id"):
            with self.subTest(label=label):
                payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
                if label == "rule id":
                    payload["rules"][0]["id"] = " harness-core "
                elif label == "path":
                    payload["rules"][0]["patterns"][0] = "\u00a0harness/README.md"
                elif label == "risk":
                    payload["rules"][0]["risks"][0] = "scope\n"
                else:
                    payload["riskChecks"]["scope"][0] = "scope.allowed-paths\n"

                with tempfile.TemporaryDirectory() as directory:
                    policy_path = Path(directory) / "policy.json"
                    policy_path.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8",
                    )

                    with self.assertRaises(HARNESS.HarnessViolation) as raised:
                        HARNESS.load_risk_policy(policy_path)

                self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
                self.assertEqual("policy.schema", raised.exception.check_id)

    def test_policy_rejects_noncanonical_repository_paths(self) -> None:
        for pattern in (
            ".",
            "docs/./x.md",
            "docs/x.md/",
            "docs/\x00x.md",
            "docs/\x1fx.md",
            "docs/\x7fx.md",
        ):
            with self.subTest(pattern=repr(pattern)):
                payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
                payload["rules"][0]["patterns"][0] = pattern

                with tempfile.TemporaryDirectory() as directory:
                    policy_path = Path(directory) / "policy.json"
                    policy_path.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8",
                    )

                    with self.assertRaises(HARNESS.HarnessViolation) as raised:
                        HARNESS.load_risk_policy(policy_path)

                self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
                self.assertEqual("policy.schema", raised.exception.check_id)

    def test_policy_rejects_duplicate_pattern_across_rules(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["rules"][1]["patterns"].append(payload["rules"][0]["patterns"][0])

        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(HARNESS.HarnessViolation, "중복 pattern"):
                HARNESS.load_risk_policy(policy_path)

    def test_policy_rejects_unknown_implemented_check(self) -> None:
        payload = json.loads(SOURCE_POLICY.read_text(encoding="utf-8"))
        payload["implementedChecks"].append("oracle.unknown")

        with tempfile.TemporaryDirectory() as directory:
            policy_path = Path(directory) / "policy.json"
            policy_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(HARNESS.HarnessViolation, "riskChecks에 없는"):
                HARNESS.load_risk_policy(policy_path)


class ScopeRiskTest(unittest.TestCase):
    def test_scope_implicitly_allows_selected_plan_path(self) -> None:
        plan = make_plan()

        self.assertEqual(
            (),
            HARNESS.scope_violations(
                (plan.relative_path, "AGENTS.md"),
                plan,
            ),
        )

    def test_scope_reports_sorted_tracked_and_untracked_outside_paths(self) -> None:
        plan = make_plan()

        self.assertEqual(
            ("README.md", "new.txt"),
            HARNESS.scope_violations(
                ("new.txt", "README.md", "new.txt", "AGENTS.md"),
                plan,
            ),
        )

    def test_risk_classification_unions_overlapping_rules(self) -> None:
        policy = make_policy(
            rules=(
                HARNESS.RiskRule(
                    rule_id="java-source",
                    patterns=("src/main/java/**",),
                    risks=("architecture",),
                ),
                HARNESS.RiskRule(
                    rule_id="order-source",
                    patterns=("src/main/java/com/example/coffee/order/**",),
                    risks=("async",),
                ),
            )
        )

        classification = HARNESS.classify_risks(
            ("src/main/java/com/example/coffee/order/Order.java",),
            policy,
        )

        self.assertEqual(("architecture", "async"), classification.detected_risks)
        self.assertEqual((), classification.unclassified_paths)

    def test_source_policy_classifies_api_document_with_completion(self) -> None:
        classification = HARNESS.classify_risks(
            ("docs/api-spec.md",),
            HARNESS.load_risk_policy(SOURCE_POLICY),
        )

        self.assertEqual(("api", "completion"), classification.detected_risks)
        self.assertEqual((), classification.unclassified_paths)

    def test_source_policy_classifies_table_document_with_completion(self) -> None:
        classification = HARNESS.classify_risks(
            ("docs/table-spec.md",),
            HARNESS.load_risk_policy(SOURCE_POLICY),
        )

        self.assertEqual(
            ("completion", "migration"),
            classification.detected_risks,
        )
        self.assertEqual((), classification.unclassified_paths)

    def test_unclassified_path_requires_replan_before_declaration_check(self) -> None:
        classification = HARNESS.classify_risks(
            ("unknown/new.file",),
            make_policy(),
        )

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_risk_declarations(make_plan(), classification)

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("risk.classification", raised.exception.check_id)
        self.assertIn("미분류", raised.exception.reason)
        self.assertIn("unknown/new.file", raised.exception.reason)

    def test_detected_but_undeclared_risk_requires_replan(self) -> None:
        policy = make_policy(
            rules=(
                HARNESS.RiskRule(
                    rule_id="api-document",
                    patterns=("docs/api-spec.md",),
                    risks=("api",),
                ),
            )
        )
        classification = HARNESS.classify_risks(("docs/api-spec.md",), policy)

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_risk_declarations(
                make_plan(declared_risks=("scope",)),
                classification,
            )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("risk.declaration", raised.exception.check_id)
        self.assertIn("api", raised.exception.reason)

    def test_changed_protected_path_requires_contract_declaration(self) -> None:
        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_contract_changes(
                ("scripts/agent-harness.py",),
                make_plan(),
                make_policy(),
            )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("trust-root.contract", raised.exception.check_id)

    def test_contract_declaration_near_matches_are_not_accepted(self) -> None:
        cases = (
            ("scripts/agent-harness.py-malicious v1", "trust-root.contract"),
            ("not scripts/agent-harness.py changed", "plan.contract-changes"),
        )
        for declaration, expected_check_id in cases:
            with self.subTest(declaration=declaration):
                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.validate_contract_changes(
                        ("scripts/agent-harness.py",),
                        make_plan(contract_changes=(declaration,)),
                        make_policy(),
                    )

                self.assertEqual(
                    HARNESS.State.REPLAN_REQUIRED,
                    raised.exception.state,
                )
                self.assertEqual(expected_check_id, raised.exception.check_id)

    def test_exact_contract_declaration_is_accepted(self) -> None:
        HARNESS.validate_contract_changes(
            ("scripts/agent-harness.py",),
            make_plan(contract_changes=("scripts/agent-harness.py v1",)),
            make_policy(),
        )

    def test_public_validation_functions_keep_approved_positional_contract(self) -> None:
        self.assertEqual(
            ("plan", "classification"),
            tuple(inspect.signature(HARNESS.validate_risk_declarations).parameters),
        )
        self.assertEqual(
            ("changed_paths", "plan", "policy"),
            tuple(inspect.signature(HARNESS.validate_contract_changes).parameters),
        )

        classification = HARNESS.RiskClassification(
            detected_risks=(),
            unclassified_paths=("unknown/new.file",),
        )
        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_risk_declarations(make_plan(), classification)

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("risk.classification", raised.exception.check_id)

    def test_existing_migration_actual_modify_fails(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        existing_path = "src/main/resources/db/migration/V1__fixture.sql"
        (fixture.work / existing_path).write_text(
            "create table fixture(id varchar(255));\n",
            encoding="utf-8",
        )
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_existing_migrations_immutable(
                fixture.work,
                context,
                changed_paths,
            )

        self.assertIn(existing_path, changed_paths)
        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("migration.immutable", raised.exception.check_id)
        self.assertIn(existing_path, raised.exception.reason)

    def test_existing_migration_actual_delete_fails(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        existing_path = "src/main/resources/db/migration/V1__fixture.sql"
        (fixture.work / existing_path).unlink()
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_existing_migrations_immutable(
                fixture.work,
                context,
                changed_paths,
            )

        self.assertIn(existing_path, changed_paths)
        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("migration.immutable", raised.exception.check_id)

    def test_existing_migration_actual_rename_fails(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        existing_path = "src/main/resources/db/migration/V1__fixture.sql"
        renamed_path = "src/main/resources/db/migration/V2__renamed.sql"
        git(fixture.work, "mv", existing_path, renamed_path)
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_existing_migrations_immutable(
                fixture.work,
                context,
                changed_paths,
            )

        self.assertIn(existing_path, changed_paths)
        self.assertIn(renamed_path, changed_paths)
        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("migration.immutable", raised.exception.check_id)

    def test_new_untracked_migration_is_allowed(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        new_path = "src/main/resources/db/migration/V2__new.sql"
        (fixture.work / new_path).write_text(
            "alter table fixture add column name varchar(255);\n",
            encoding="utf-8",
        )
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        self.assertIn(new_path, changed_paths)
        HARNESS.validate_existing_migrations_immutable(
            fixture.work,
            context,
            changed_paths,
        )

    def test_copied_new_migration_does_not_mutate_unchanged_source(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        source_path = "src/main/resources/db/migration/V1__fixture.sql"
        copied_path = "src/main/resources/db/migration/V2__copied.sql"
        (fixture.work / copied_path).write_bytes(
            (fixture.work / source_path).read_bytes()
        )
        git(fixture.work, "add", copied_path)
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        self.assertIn(source_path, changed_paths)
        self.assertIn(copied_path, changed_paths)
        HARNESS.validate_existing_migrations_immutable(
            fixture.work,
            context,
            changed_paths,
        )

    def test_migration_validator_rejects_actual_mutation_missing_from_report(
        self,
    ) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        existing_path = "src/main/resources/db/migration/V1__fixture.sql"
        (fixture.work / existing_path).write_text(
            "create table fixture(id varchar(255));\n",
            encoding="utf-8",
        )

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_existing_migrations_immutable(
                fixture.work,
                context,
                (),
            )

        self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
        self.assertEqual("git.diff", raised.exception.check_id)

    def test_migration_base_tree_lookup_failure_is_blocked(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context(merge_base_sha="f" * 40)

        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_existing_migrations_immutable(
                fixture.work,
                context,
                ("src/main/resources/db/migration/V2__new.sql",),
            )

        self.assertEqual(HARNESS.State.BLOCKED, raised.exception.state)
        self.assertEqual("git.repository", raised.exception.check_id)

    def test_collect_local_changed_paths_includes_every_change_kind(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        fixture.create_all_change_kinds()

        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        self.assertTrue(
            {
                "committed.txt",
                "staged.txt",
                "tracked.txt",
                "untracked.txt",
                "rename-old.txt",
                "rename-new.txt",
            }.issubset(changed_paths),
            changed_paths,
        )

    def test_collect_local_changed_paths_preserves_staged_copy_source_and_target(
        self,
    ) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        source_path = "tracked.txt"
        target_path = "copy.txt"
        (fixture.work / target_path).write_bytes(
            (fixture.work / source_path).read_bytes()
        )
        git(fixture.work, "add", target_path)
        raw_copy_status = HARNESS.run_git(
            fixture.work,
            "diff",
            "--cached",
            "--name-status",
            "-z",
            "--find-renames",
            "--find-copies-harder",
            "--",
        )

        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        self.assertTrue(raw_copy_status.startswith(b"C"), raw_copy_status)
        self.assertEqual(
            (source_path, target_path),
            HARNESS.parse_name_status(raw_copy_status),
        )
        self.assertIn(source_path, changed_paths)
        self.assertIn(target_path, changed_paths)


class GitStateTest(unittest.TestCase):
    def test_branch_issue_mismatch_requires_replan(self) -> None:
        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_branch("feature/124-agent-harness-core", 123)

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("git.branch", raised.exception.check_id)
        self.assertIn("123", raised.exception.reason)
        self.assertIn("124", raised.exception.reason)

    def test_branch_name_accepts_only_positive_issue_and_lowercase_kebab(self) -> None:
        accepted = (
            ("feature/1-a", 1),
            ("fix/23-x9", 23),
            ("refactor/42-agent-harness-core", 42),
            ("docs/9-api-v2", 9),
        )
        rejected = (
            ("", 1),
            ("main", 1),
            ("feature/0-a", 0),
            ("feature/01-a", 1),
            ("feature/1-Agent", 1),
            ("feature/1-agent_harness", 1),
            ("feature/1-agent-", 1),
            ("chore/1-agent", 1),
        )

        for branch, issue in accepted:
            with self.subTest(branch=branch):
                HARNESS.validate_branch(branch, issue)
        for branch, issue in rejected:
            with self.subTest(branch=branch):
                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.validate_branch(branch, issue)
                self.assertEqual(
                    HARNESS.State.REPLAN_REQUIRED,
                    raised.exception.state,
                )
                self.assertEqual("git.branch", raised.exception.check_id)

    def test_parse_name_status_preserves_both_rename_and_copy_paths(self) -> None:
        raw = (
            b"R100\0rename-old.txt\0rename-new.txt\0"
            b"C75\0copy-source.txt\0copy-target.txt\0"
            b"M\0plain.txt\0"
        )

        self.assertEqual(
            (
                "rename-old.txt",
                "rename-new.txt",
                "copy-source.txt",
                "copy-target.txt",
                "plain.txt",
            ),
            HARNESS.parse_name_status(raw),
        )

    def test_parse_name_status_rejects_malformed_token_stream(self) -> None:
        for raw in (
            b"R100\0only-old.txt\0",
            b"M\0",
            b"M\0path-without-final-nul",
            b"INVALID\0path.txt\0",
            b"\xff\0path.txt\0",
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.parse_name_status(raw)
                self.assertEqual(HARNESS.State.FAIL, raised.exception.state)
                self.assertEqual("git.diff", raised.exception.check_id)

    def test_prepare_rejects_dirty_path_other_than_selected_plan(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_and_add_outside_path()

        state, checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, state)
        self.assertTrue(
            any("outside.md" in check.reason for check in checks),
            checks,
        )

    def test_prepare_allows_only_selected_plan_to_be_dirty(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        plan_path = fixture.work / fixture.plan()
        plan_path.write_bytes(plan_path.read_bytes() + b"\n")

        state, checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )

        self.assertEqual(HARNESS.State.PASS, state)
        self.assertEqual(HARNESS.State.PASS, checks[-1].state)
        self.assertEqual("prepare", checks[-1].check_id)

    def test_prepare_writes_lowercase_sha_identity_to_plan_lock(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)

        state, _checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )
        payload = json.loads(
            (fixture.work / "build" / "harness" / "plan.lock.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(HARNESS.State.PASS, state)
        self.assertRegex(payload["baseTipSha"], r"^[0-9a-f]{40}$")
        self.assertRegex(payload["mergeBaseSha"], r"^[0-9a-f]{40}$")

    def test_prepare_does_not_write_lock_when_preflight_is_blocked(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)

        def blocked_preflight(root: Path) -> tuple[object, ...]:
            return fixture_preflight(root, HARNESS.State.BLOCKED)

        state, checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=blocked_preflight,
        )

        self.assertEqual(HARNESS.State.BLOCKED, state)
        self.assertTrue(
            any(
                check.check_id == "environment.docker"
                and check.state is HARNESS.State.BLOCKED
                for check in checks
            ),
            checks,
        )
        self.assertFalse(
            (fixture.work / "build" / "harness" / "plan.lock.json").exists()
        )

    def test_prepare_rejects_symlinked_evidence_parent_without_touching_outside(
        self,
    ) -> None:
        for parent_component in ("build", "harness"):
            for preflight_state in (HARNESS.State.BLOCKED, HARNESS.State.PASS):
                with self.subTest(
                    parent_component=parent_component,
                    preflight_state=preflight_state.name,
                ):
                    fixture = GitFixture()
                    self.addCleanup(fixture.close)
                    outside = fixture.base / f"outside-{parent_component}"
                    sentinel_bytes = b"external sentinel\n"

                    if parent_component == "build":
                        sentinel = outside / "harness" / "plan.lock.json"
                        sentinel.parent.mkdir(parents=True)
                        (fixture.work / "build").symlink_to(
                            outside,
                            target_is_directory=True,
                        )
                    else:
                        sentinel = outside / "plan.lock.json"
                        outside.mkdir()
                        (fixture.work / "build").mkdir()
                        (fixture.work / "build" / "harness").symlink_to(
                            outside,
                            target_is_directory=True,
                        )
                    sentinel.write_bytes(sentinel_bytes)

                    def preflight(root: Path) -> tuple[object, ...]:
                        return fixture_preflight(root, preflight_state)

                    state, checks = HARNESS.prepare(
                        fixture.work,
                        fixture.plan(),
                        preflight=preflight,
                    )

                    self.assertNotEqual(HARNESS.State.PASS, state)
                    self.assertEqual("evidence.path", checks[0].check_id)
                    self.assertEqual(sentinel_bytes, sentinel.read_bytes())

    def test_prepare_revalidates_identity_and_clean_state_after_preflight(self) -> None:
        cases = (
            ("outside path", HARNESS.State.REPLAN_REQUIRED, "git.clean"),
            ("plan hash", HARNESS.State.REPLAN_REQUIRED, "plan.lock"),
            ("base tip", HARNESS.State.REPLAN_REQUIRED, "plan.lock"),
        )
        for mutation, expected_state, expected_check_id in cases:
            with self.subTest(mutation=mutation):
                fixture = GitFixture()
                self.addCleanup(fixture.close)

                def mutating_preflight(root: Path) -> tuple[object, ...]:
                    if mutation == "outside path":
                        (root / "outside.md").write_text(
                            "outside\n",
                            encoding="utf-8",
                        )
                    elif mutation == "plan hash":
                        plan_path = root / fixture.plan()
                        plan_path.write_bytes(plan_path.read_bytes() + b"\n")
                    else:
                        fixture.advance_origin_main_without_merging()
                    return passing_preflight(root)

                state, checks = HARNESS.prepare(
                    fixture.work,
                    fixture.plan(),
                    preflight=mutating_preflight,
                )

                self.assertEqual(expected_state, state)
                self.assertEqual(expected_check_id, checks[0].check_id)
                self.assertFalse(
                    (
                        fixture.work
                        / "build"
                        / "harness"
                        / "plan.lock.json"
                    ).exists()
                )

    def test_prepare_rejects_invalid_preflight_result_schema(self) -> None:
        cases = ("empty", "partial", "duplicate")
        for malformed in cases:
            with self.subTest(malformed=malformed):
                fixture = GitFixture()
                self.addCleanup(fixture.close)

                def malformed_preflight(root: Path) -> tuple[object, ...]:
                    checks = passing_preflight(root)
                    if malformed == "empty":
                        return ()
                    if malformed == "partial":
                        return checks[:-1]
                    return (checks[0], checks[0], *checks[1:])

                state, checks = HARNESS.prepare(
                    fixture.work,
                    fixture.plan(),
                    preflight=malformed_preflight,
                )

                self.assertEqual(HARNESS.State.FAIL, state)
                self.assertEqual("environment.preflight", checks[0].check_id)
                self.assertFalse(
                    (
                        fixture.work
                        / "build"
                        / "harness"
                        / "plan.lock.json"
                    ).exists()
                )

    def test_print_checks_escapes_newline_and_ansi_from_dirty_path(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        forged_path = "outside\n[PASS] forged: accepted\x1b[31m"
        (fixture.work / forged_path).write_text("outside\n", encoding="utf-8")
        state, checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )
        output = io.StringIO()

        with redirect_stdout(output):
            HARNESS.print_checks(checks)

        rendered = output.getvalue()
        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, state)
        self.assertEqual(1, len(rendered.splitlines()))
        self.assertNotIn("\x1b", rendered)
        self.assertIn(r"\n", rendered)
        self.assertIn(r"\x1b", rendered)

    def test_plan_lock_rejects_duplicate_fields_and_untrusted_strings(self) -> None:
        valid_payload = {
            "schemaVersion": 1,
            "issue": 123,
            "planPath": "harness/plans/123.json",
            "planHash": "a" * 64,
            "targetBranch": "main",
            "branch": "feature/123-agent-harness-core",
            "baseTipSha": "b" * 40,
            "mergeBaseSha": "c" * 40,
        }
        cases: dict[str, bytes] = {}
        encoded = json.dumps(valid_payload, separators=(",", ":")).encode("utf-8")
        cases["duplicate"] = encoded.replace(
            b'"issue":123',
            b'"issue":123,"issue":123',
            1,
        )
        extra_field = dict(valid_payload)
        extra_field["candidateHeadSha"] = "d" * 40
        cases["field"] = json.dumps(extra_field).encode("utf-8")
        whitespace = dict(valid_payload)
        whitespace["branch"] = " feature/123-agent-harness-core"
        cases["whitespace"] = json.dumps(whitespace).encode("utf-8")
        uppercase_sha = dict(valid_payload)
        uppercase_sha["baseTipSha"] = "B" * 40
        cases["uppercase sha"] = json.dumps(uppercase_sha).encode("utf-8")
        short_sha = dict(valid_payload)
        short_sha["mergeBaseSha"] = "c" * 39
        cases["short sha"] = json.dumps(short_sha).encode("utf-8")

        for label, raw in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "plan.lock.json"
                path.write_bytes(raw)

                with self.assertRaises(HARNESS.HarnessViolation) as raised:
                    HARNESS.load_plan_lock(path)

                self.assertEqual(
                    HARNESS.State.REPLAN_REQUIRED,
                    raised.exception.state,
                )
                self.assertEqual("plan.lock", raised.exception.check_id)

    def test_plan_lock_detects_base_tip_drift_even_when_merge_base_is_same(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        state, _checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )
        self.assertEqual(HARNESS.State.PASS, state)

        policy = fixture.policy()
        plan = HARNESS.load_plan(fixture.work, fixture.plan(), policy)
        lock = HARNESS.load_plan_lock(
            fixture.work / "build" / "harness" / "plan.lock.json"
        )
        original_context = HARNESS.resolve_local_git_context(fixture.work, plan)
        fixture.advance_origin_main_without_merging()
        git(fixture.work, "fetch", "origin", "main")
        current_context = HARNESS.resolve_local_git_context(fixture.work, plan)

        self.assertEqual(
            original_context.merge_base_sha,
            current_context.merge_base_sha,
        )
        self.assertNotEqual(
            original_context.base_tip_sha,
            current_context.base_tip_sha,
        )
        with self.assertRaises(HARNESS.HarnessViolation) as raised:
            HARNESS.validate_plan_lock(lock, plan, current_context)

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, raised.exception.state)
        self.assertEqual("plan.lock", raised.exception.check_id)
        self.assertIn("base tip", raised.exception.reason)


class EvaluationTest(unittest.TestCase):
    def test_aggregate_state_uses_fail_closed_priority(self) -> None:
        cases = (
            ((), HARNESS.State.PASS),
            ((HARNESS.State.PASS,), HARNESS.State.PASS),
            ((HARNESS.State.PASS, HARNESS.State.BLOCKED), HARNESS.State.BLOCKED),
            ((HARNESS.State.BLOCKED, HARNESS.State.FAIL), HARNESS.State.FAIL),
            (
                (
                    HARNESS.State.FAIL,
                    HARNESS.State.REPLAN_REQUIRED,
                    HARNESS.State.BLOCKED,
                ),
                HARNESS.State.REPLAN_REQUIRED,
            ),
        )

        for states, expected in cases:
            with self.subTest(states=states):
                checks = tuple(
                    HARNESS.CheckResult(f"check.{index}", state, "fixture")
                    for index, state in enumerate(states)
                )
                self.assertEqual(expected, HARNESS.aggregate_state(checks))

    def test_cli_argument_errors_are_fail_with_single_line_diagnostic(self) -> None:
        cases = (
            (),
            ("prepare",),
            ("evaluate",),
            ("prepare", "plan.json", "extra"),
            ("unknown",),
        )

        for argv in cases:
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    exit_code = HARNESS.main(argv)

                self.assertEqual(1, exit_code)
                self.assertEqual(1, len(stderr.getvalue().splitlines()))
                self.assertIn("[FAIL] cli.arguments", stderr.getvalue())

    def test_diff_hash_changes_when_untracked_content_changes(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        untracked = fixture.work / "untracked.txt"
        untracked.write_text("one\n", encoding="utf-8")
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )

        first = HARNESS.compute_diff_hash(fixture.work, context, changed_paths)
        untracked.write_text("two\n", encoding="utf-8")
        second = HARNESS.compute_diff_hash(fixture.work, context, changed_paths)

        self.assertRegex(first, r"^[0-9a-f]{64}$")
        self.assertNotEqual(first, second)

    def test_evaluate_scope_violation_writes_replan_evidence(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_and_add_outside_path()
        runner_called = False

        def should_not_run(_root: Path, _check_ids: tuple[str, ...]) -> tuple[object, ...]:
            nonlocal runner_called
            runner_called = True
            return ()

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=should_not_run,
        )
        evidence_path = fixture.work / "build" / "harness" / "evaluation.json"
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertFalse(runner_called)
        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
        self.assertEqual("REPLAN_REQUIRED", payload["state"])
        self.assertIn("outside.md", payload["changedPaths"])
        self.assertRegex(payload["diffHash"], r"^[0-9a-f]{64}$")

    def test_passing_evaluation_serializes_complete_identity(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=passing_required_checks,
        )
        payload = evaluation.to_dict()

        self.assertEqual(HARNESS.State.PASS, evaluation.state)
        self.assertEqual(
            {
                "schemaVersion",
                "state",
                "baseTipSha",
                "mergeBaseSha",
                "candidateHeadSha",
                "testedRevisionSha",
                "planPath",
                "planHash",
                "declaredRisks",
                "detectedRisks",
                "changedPaths",
                "diffHash",
                "checks",
            },
            set(payload),
        )
        self.assertRegex(payload["baseTipSha"], r"^[0-9a-f]{40}$")
        self.assertRegex(payload["mergeBaseSha"], r"^[0-9a-f]{40}$")
        self.assertRegex(payload["candidateHeadSha"], r"^[0-9a-f]{40}$")
        self.assertEqual(payload["candidateHeadSha"], payload["testedRevisionSha"])
        self.assertEqual(fixture.plan().as_posix(), payload["planPath"])
        self.assertRegex(payload["planHash"], r"^[0-9a-f]{64}$")
        self.assertEqual(["completion"], payload["declaredRisks"])
        self.assertEqual(["completion"], payload["detectedRisks"])
        self.assertEqual(["AGENTS.md"], payload["changedPaths"])
        self.assertRegex(payload["diffHash"], r"^[0-9a-f]{64}$")
        self.assertTrue(payload["checks"])
        self.assertEqual(
            {
                "id",
                "state",
                "reason",
                "command",
                "exitCode",
                "durationMs",
            },
            set(payload["checks"][0]),
        )

    def test_runner_committing_same_diff_requires_replan(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()

        def committing_runner(
            root: Path,
            check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            git(root, "add", "AGENTS.md")
            git(root, "commit", "-m", "runner changed HEAD")
            return passing_required_checks(root, check_ids)

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=committing_runner,
        )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
        freshness = [
            check for check in evaluation.checks if check.check_id == "evidence.freshness"
        ]
        self.assertEqual(1, len(freshness))
        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, freshness[0].state)
        self.assertIn("HEAD", freshness[0].reason)

    def test_check_runner_results_are_validated_fail_closed(self) -> None:
        cases = ("empty", "missing", "duplicate", "extra", "non-check-result")

        for malformed in cases:
            with self.subTest(malformed=malformed):
                fixture = GitFixture()
                self.addCleanup(fixture.close)
                fixture.prepare_scope_only_change()

                def malformed_runner(
                    _root: Path,
                    check_ids: tuple[str, ...],
                ) -> tuple[object, ...]:
                    valid = tuple(
                        HARNESS.CheckResult(
                            check_id,
                            HARNESS.State.PASS,
                            "fixture pass",
                        )
                        for check_id in check_ids
                    )
                    if malformed == "empty":
                        return ()
                    if malformed == "missing":
                        return valid[:-1]
                    if malformed == "duplicate":
                        return (*valid, valid[0])
                    if malformed == "extra":
                        return (
                            *valid,
                            HARNESS.CheckResult(
                                "unknown.extra",
                                HARNESS.State.PASS,
                                "forged",
                            ),
                        )
                    return (*valid, "not a CheckResult")

                evaluation = HARNESS.evaluate(
                    fixture.work,
                    fixture.plan(),
                    check_runner=malformed_runner,
                )
                evidence = json.loads(
                    (
                        fixture.work / "build" / "harness" / "evaluation.json"
                    ).read_text(encoding="utf-8")
                )

                self.assertNotEqual(HARNESS.State.PASS, evaluation.state)
                self.assertTrue(
                    any(
                        check.check_id == "checks.runner"
                        and check.state is HARNESS.State.FAIL
                        for check in evaluation.checks
                    ),
                    evaluation.checks,
                )
                self.assertTrue(
                    any(check["id"] == "checks.runner" for check in evidence["checks"])
                )

    def test_gradle_result_without_preflight_results_fails_closed(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()

        def requested_only_runner(
            _root: Path,
            check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            return tuple(
                HARNESS.CheckResult(check_id, HARNESS.State.PASS, "fixture pass")
                for check_id in check_ids
            )

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=requested_only_runner,
        )
        runner_checks = [
            check for check in evaluation.checks if check.check_id == "checks.runner"
        ]

        self.assertEqual(HARNESS.State.FAIL, evaluation.state)
        self.assertEqual(1, len(runner_checks))
        runner_check = runner_checks[0]
        self.assertEqual(HARNESS.State.FAIL, runner_check.state)
        for check_id in REQUIRED_PREFLIGHT_IDS:
            self.assertIn(check_id, runner_check.reason)

    def test_preflight_results_are_not_required_without_gradle_request(self) -> None:
        raw_checks = (
            HARNESS.CheckResult("harness.unit", HARNESS.State.PASS, "fixture pass"),
        )

        checks, error = HARNESS.validate_check_runner_results(
            raw_checks,
            ("harness.unit",),
        )

        self.assertEqual(raw_checks, checks)
        self.assertIsNone(error)

    def test_runner_exception_after_commit_still_records_replan_freshness(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()

        def committing_then_failing(
            root: Path,
            _check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            git(root, "add", "AGENTS.md")
            git(root, "commit", "-m", "runner changed HEAD before failure")
            raise RuntimeError("runner exploded")

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=committing_then_failing,
        )

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
        self.assertTrue(
            any(
                check.check_id == "harness.internal"
                and check.state is HARNESS.State.FAIL
                for check in evaluation.checks
            )
        )
        self.assertTrue(
            any(
                check.check_id == "evidence.freshness"
                and check.state is HARNESS.State.REPLAN_REQUIRED
                for check in evaluation.checks
            )
        )

    def test_write_json_atomic_escapes_invalid_utf8_surrogate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"

            HARNESS.write_json_atomic(path, {"changedPaths": ["bad\udcff"]})
            raw = path.read_bytes()
            payload = json.loads(raw.decode("utf-8"))

        self.assertEqual("bad\udcff", payload["changedPaths"][0])
        self.assertIn(b"\\udcff", raw)

    def test_evaluate_rejects_preexisting_symlinked_evidence_parent(self) -> None:
        for parent_component in ("build", "harness"):
            with self.subTest(parent_component=parent_component):
                fixture = GitFixture()
                self.addCleanup(fixture.close)
                fixture.prepare_scope_only_change()
                outside = fixture.base / f"outside-{parent_component}"
                sentinel_bytes = b"external sentinel\n"

                if parent_component == "build":
                    shutil.rmtree(fixture.work / "build")
                    sentinel = outside / "harness" / "evaluation.json"
                    sentinel.parent.mkdir(parents=True)
                    (fixture.work / "build").symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                else:
                    shutil.rmtree(fixture.work / "build" / "harness")
                    sentinel = outside / "evaluation.json"
                    outside.mkdir()
                    (fixture.work / "build" / "harness").symlink_to(
                        outside,
                        target_is_directory=True,
                    )
                sentinel.write_bytes(sentinel_bytes)

                evaluation = HARNESS.evaluate(
                    fixture.work,
                    fixture.plan(),
                    check_runner=passing_required_checks,
                )

                self.assertEqual(HARNESS.State.FAIL, evaluation.state)
                self.assertEqual("evidence.path", evaluation.checks[0].check_id)
                self.assertEqual(sentinel_bytes, sentinel.read_bytes())

    def test_evaluate_rechecks_evidence_parent_after_runner(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()
        outside = fixture.base / "outside-swap"
        outside.mkdir()
        sentinel = outside / "evaluation.json"
        sentinel_bytes = b"external sentinel\n"
        sentinel.write_bytes(sentinel_bytes)

        def swapping_runner(
            root: Path,
            check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            shutil.rmtree(root / "build" / "harness")
            (root / "build" / "harness").symlink_to(
                outside,
                target_is_directory=True,
            )
            return passing_required_checks(root, check_ids)

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=swapping_runner,
        )

        self.assertEqual(HARNESS.State.FAIL, evaluation.state)
        self.assertTrue(
            any(check.check_id == "evidence.path" for check in evaluation.checks)
        )
        self.assertEqual(sentinel_bytes, sentinel.read_bytes())

    def test_evaluate_restores_validated_plan_lock_removed_by_clean_check(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()
        lock_path = fixture.work / "build" / "harness" / "plan.lock.json"
        expected_lock = json.loads(lock_path.read_text(encoding="utf-8"))

        def clean_build_runner(
            root: Path,
            check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            shutil.rmtree(root / "build")
            return passing_required_checks(root, check_ids)

        first = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=clean_build_runner,
        )

        self.assertEqual(HARNESS.State.PASS, first.state)
        self.assertTrue(lock_path.is_file())
        self.assertEqual(
            expected_lock,
            json.loads(lock_path.read_text(encoding="utf-8")),
        )

        second = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=passing_required_checks,
        )
        self.assertEqual(HARNESS.State.PASS, second.state)

    def test_evaluate_does_not_restore_stale_lock_after_plan_drift(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        fixture.prepare_scope_only_change()
        lock_path = fixture.work / "build" / "harness" / "plan.lock.json"

        def cleaning_and_drifting_runner(
            root: Path,
            check_ids: tuple[str, ...],
        ) -> tuple[object, ...]:
            shutil.rmtree(root / "build")
            selected_plan = root / fixture.plan()
            selected_plan.write_bytes(selected_plan.read_bytes() + b"\n")
            return passing_required_checks(root, check_ids)

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=cleaning_and_drifting_runner,
        )
        evidence_path = fixture.work / "build" / "harness" / "evaluation.json"

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
        self.assertFalse(lock_path.exists())
        self.assertEqual(
            "REPLAN_REQUIRED",
            json.loads(evidence_path.read_text(encoding="utf-8"))["state"],
        )

    def test_evaluate_removes_stale_pass_before_writing_new_result(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        state, _checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=passing_preflight,
        )
        self.assertEqual(HARNESS.State.PASS, state)
        evidence_path = fixture.work / "build" / "harness" / "evaluation.json"
        evidence_path.write_text('{"state":"PASS","stale":true}\n', encoding="utf-8")
        (fixture.work / "outside.md").write_text("outside\n", encoding="utf-8")

        evaluation = HARNESS.evaluate(
            fixture.work,
            fixture.plan(),
            check_runner=passing_required_checks,
        )
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))

        self.assertEqual(HARNESS.State.REPLAN_REQUIRED, evaluation.state)
        self.assertEqual("REPLAN_REQUIRED", payload["state"])
        self.assertNotIn("stale", payload)

    def test_diff_hash_tracks_tracked_content_and_symlink_target_string(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)
        context = fixture.context()
        tracked = fixture.work / "tracked.txt"

        clean_hash = HARNESS.compute_diff_hash(fixture.work, context, ())
        tracked.write_text("unstaged one\n", encoding="utf-8")
        changed_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )
        unstaged_hash = HARNESS.compute_diff_hash(
            fixture.work,
            context,
            changed_paths,
        )
        git(fixture.work, "add", "tracked.txt")
        staged_hash = HARNESS.compute_diff_hash(
            fixture.work,
            context,
            changed_paths,
        )
        tracked.write_text("unstaged two\n", encoding="utf-8")
        mixed_hash = HARNESS.compute_diff_hash(
            fixture.work,
            context,
            changed_paths,
        )

        self.assertNotEqual(clean_hash, unstaged_hash)
        self.assertEqual(unstaged_hash, staged_hash)
        self.assertNotEqual(staged_hash, mixed_hash)

        target = fixture.base / "target-a"
        target.write_text("one\n", encoding="utf-8")
        link = fixture.work / "untracked-link"
        link.symlink_to(os.path.relpath(target, fixture.work))
        link_paths = HARNESS.collect_local_changed_paths(
            fixture.work,
            context.merge_base_sha,
        )
        link_hash = HARNESS.compute_diff_hash(fixture.work, context, link_paths)
        target.write_text("two\n", encoding="utf-8")
        same_target_hash = HARNESS.compute_diff_hash(
            fixture.work,
            context,
            link_paths,
        )
        other_target = fixture.base / "target-b"
        other_target.write_text("two\n", encoding="utf-8")
        link.unlink()
        link.symlink_to(os.path.relpath(other_target, fixture.work))
        other_target_hash = HARNESS.compute_diff_hash(
            fixture.work,
            context,
            link_paths,
        )

        self.assertEqual(link_hash, same_target_hash)
        self.assertNotEqual(link_hash, other_target_hash)

    def test_required_check_ids_are_unique_and_unimplemented_oracle_blocks(self) -> None:
        policy = HARNESS.load_risk_policy(SOURCE_POLICY)
        plan = make_plan(declared_risks=("scope", "completion", "concurrency"))
        classification = HARNESS.RiskClassification(
            detected_risks=("scope", "concurrency"),
            unclassified_paths=(),
        )

        check_ids = HARNESS.required_check_ids(plan, classification, policy)
        oracle_results = HARNESS.run_required_checks(
            REPO_ROOT,
            ("oracle.cross-domain-concurrency",),
        )

        self.assertEqual("harness.unit", check_ids[0])
        self.assertEqual("gradle.test", check_ids[1])
        self.assertEqual(len(check_ids), len(set(check_ids)))
        self.assertIn("oracle.cross-domain-concurrency", check_ids)
        self.assertNotIn("scope.allowed-paths", check_ids)
        self.assertNotIn("risk.classification", check_ids)
        self.assertNotIn("risk.declaration", check_ids)
        self.assertEqual(1, len(oracle_results))
        self.assertEqual(HARNESS.State.BLOCKED, oracle_results[0].state)

    def test_execute_command_records_output_status_and_environment(self) -> None:
        success = HARNESS.execute_command(
            REPO_ROOT,
            "command.success",
            (
                sys.executable,
                "-c",
                "import os; print(os.environ.get('PYTHONDONTWRITEBYTECODE'))",
            ),
        )
        failure = HARNESS.execute_command(
            REPO_ROOT,
            "command.failure",
            (sys.executable, "-c", "import sys; print('nope'); sys.exit(7)"),
        )
        docker_blocked = HARNESS.execute_command(
            REPO_ROOT,
            "gradle.test",
            (
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('Could not find a valid Docker environment'); sys.exit(1)",
            ),
        )
        missing = HARNESS.execute_command(
            REPO_ROOT,
            "command.missing",
            ("definitely-not-an-agent-harness-command",),
        )

        self.assertEqual(HARNESS.State.PASS, success.state)
        self.assertIn("1", success.reason)
        self.assertEqual(0, success.exit_code)
        self.assertIsInstance(success.duration_ms, int)
        self.assertEqual(HARNESS.State.FAIL, failure.state)
        self.assertEqual(7, failure.exit_code)
        self.assertIn("nope", failure.reason)
        self.assertEqual(HARNESS.State.BLOCKED, docker_blocked.state)
        self.assertEqual(HARNESS.State.FAIL, missing.state)
        self.assertIsNone(missing.exit_code)
        self.assertEqual(
            ("definitely-not-an-agent-harness-command",),
            missing.command,
        )

    def test_harness_unit_nonzero_with_docker_message_is_fail(self) -> None:
        result = HARNESS.execute_command(
            REPO_ROOT,
            "harness.unit",
            (
                sys.executable,
                "-c",
                "import sys; sys.stderr.write('Could not find a valid Docker environment'); sys.exit(1)",
            ),
        )

        self.assertEqual(HARNESS.State.FAIL, result.state)
        self.assertEqual(1, result.exit_code)
        self.assertIn("Could not find a valid Docker environment", result.reason)

    def test_unexpected_cli_exception_includes_exception_type(self) -> None:
        stderr = io.StringIO()

        with patch.object(
            HARNESS,
            "find_git_root",
            side_effect=RuntimeError("boom"),
        ), redirect_stderr(stderr):
            exit_code = HARNESS.main(("prepare", "harness/plans/3.json"))

        self.assertEqual(1, exit_code)
        self.assertEqual(
            "[FAIL] harness.internal: 'RuntimeError: boom'\n",
            stderr.getvalue(),
        )

    def test_unexpected_prepare_exception_records_exception_type(self) -> None:
        fixture = GitFixture()
        self.addCleanup(fixture.close)

        def exploding_preflight(_root: Path) -> tuple[object, ...]:
            raise RuntimeError("boom")

        state, checks = HARNESS.prepare(
            fixture.work,
            fixture.plan(),
            preflight=exploding_preflight,
        )

        self.assertEqual(HARNESS.State.FAIL, state)
        self.assertEqual("harness.internal", checks[0].check_id)
        self.assertEqual("RuntimeError: boom", checks[0].reason)


class DocumentationTest(unittest.TestCase):
    def test_readme_documents_only_supported_commands_and_states(self) -> None:
        root = Path(__file__).resolve().parents[2]
        readme = (root / "harness/README.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        for command in (
            "python3 scripts/agent-harness.py prepare harness/plans/<issue>.json",
            "python3 scripts/agent-harness.py evaluate harness/plans/<issue>.json",
        ):
            self.assertIn(command, readme)
        for state in ("PASS", "FAIL", "BLOCKED", "REPLAN_REQUIRED"):
            self.assertIn(state, readme)
        self.assertIn("harness/README.md", agents)
        self.assertNotIn("integrity --ci", readme)
        self.assertNotIn("evaluate --ci", readme)

    def test_workflow_and_conventions_use_manifest_gate(self) -> None:
        root = Path(__file__).resolve().parents[2]
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        workflow = (root / "docs/rules/workflow.md").read_text(encoding="utf-8")
        conventions = (root / "docs/rules/conventions.md").read_text(encoding="utf-8")
        order = "Plan → Issue → Branch → Manifest → Prepare → Generate → Evaluate → Explain"
        self.assertIn(order, agents)
        self.assertIn(order, workflow)
        self.assertIn("feature|fix|refactor|docs", workflow)
        self.assertIn("PASS=0", workflow)
        self.assertIn("기존 Flyway migration은 수정하거나 삭제하지 않는다", conventions)
        self.assertIn("allowedPaths", conventions)


if __name__ == "__main__":
    unittest.main()
