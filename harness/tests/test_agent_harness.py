from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
