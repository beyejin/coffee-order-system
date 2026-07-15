from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "agent-publish.py"
SPEC = importlib.util.spec_from_file_location("agent_publish", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load agent publisher: {SCRIPT}")
PUBLISH = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PUBLISH
SPEC.loader.exec_module(PUBLISH)


def manifest_bytes(issue: int = 6) -> bytes:
    return json.dumps(
        {
            "issue": issue,
            "targetBranch": "main",
            "objective": "인기 메뉴 Redis read model 적용",
            "allowedPaths": ["README.md"],
            "acceptanceCriteria": ["검증이 통과한다."],
            "declaredRisks": ["completion"],
            "contractChanges": [],
            "nonGoals": ["검색어 API 추가"],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class FakeRunner:
    def __init__(
        self,
        evaluation_state: str = "PASS",
        pr_list: list[dict[str, object]] | None = None,
        issue_state: str = "CLOSED",
    ) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.evaluation_state = evaluation_state
        self.pr_list = pr_list or []
        self.issue_state = issue_state
        self.head = "a" * 40

    def __call__(self, command: tuple[str, ...], root: Path) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if command[:3] == ("git", "branch", "--show-current"):
            return subprocess.CompletedProcess(command, 0, "feature/6-popular-menu-redis\n", "")
        if command[:3] == ("git", "rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, f"{self.head}\n", "")
        if command[:3] == ("git", "status", "--porcelain"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if any("agent-harness.py" in item for item in command) and "evaluate" in command:
            evidence_path = root / "build" / "harness" / "evaluation.json"
            evidence_path.parent.mkdir(parents=True, exist_ok=True)
            evidence_path.write_text(
                json.dumps(
                    {
                        "state": self.evaluation_state,
                        "candidateHeadSha": self.head,
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ("gh", "repo", "view"):
            return subprocess.CompletedProcess(command, 0, "beyejin/coffee-order-system\n", "")
        if command[:3] == ("gh", "pr", "list"):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(self.pr_list),
                "",
            )
        if command[:3] == ("git", "push"):
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] == ("gh", "pr", "create"):
            return subprocess.CompletedProcess(
                command,
                0,
                "https://github.com/beyejin/coffee-order-system/pull/6\n",
                "",
            )
        if command[:3] == ("gh", "pr", "view"):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"state": "MERGED", "mergedAt": "2026-07-15T12:00:00Z"}),
                "",
            )
        if command[:3] == ("gh", "issue", "view"):
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"state": self.issue_state}),
                "",
            )
        if command[:3] == ("gh", "issue", "close"):
            self.issue_state = "CLOSED"
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "", "")


class AgentPublishTest(unittest.TestCase):
    def test_finalize_publishes_ready_pr_with_issue_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "harness" / "plans" / "issue-6-popular-menu-redis.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(manifest_bytes())
            runner = FakeRunner()

            result = PUBLISH.finalize(
                root,
                Path("harness/plans/issue-6-popular-menu-redis.json"),
                runner=runner,
            )

        self.assertEqual("READY_FOR_REVIEW", result.state)
        self.assertEqual(
            "https://github.com/beyejin/coffee-order-system/pull/6",
            result.pr_url,
        )
        create = next(command for command in runner.commands if command[:3] == ("gh", "pr", "create"))
        self.assertIn("--head", create)
        self.assertIn("feature/6-popular-menu-redis", create)
        body = create[create.index("--body") + 1]
        self.assertIn("Closes #6", body)
        self.assertNotIn("--draft", create)

    def test_finalize_stops_before_publish_when_evaluation_is_not_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "harness" / "plans" / "issue-6-popular-menu-redis.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(manifest_bytes())
            runner = FakeRunner("BLOCKED")

            with self.assertRaisesRegex(PUBLISH.PublishError, "PASS"):
                PUBLISH.finalize(
                    root,
                    Path("harness/plans/issue-6-popular-menu-redis.json"),
                    runner=runner,
                )

        self.assertFalse(any(command[:3] == ("git", "push") for command in runner.commands))
        self.assertFalse(any(command[:3] == ("gh", "pr", "create") for command in runner.commands))

    def test_finalize_merge_verifies_pr_and_issue_completion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "harness" / "plans" / "issue-6-popular-menu-redis.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(manifest_bytes())
            runner = FakeRunner()

            result = PUBLISH.finalize(
                root,
                Path("harness/plans/issue-6-popular-menu-redis.json"),
                merge=True,
                runner=runner,
            )

        self.assertEqual("COMPLETED", result.state)
        self.assertTrue(result.merged)
        self.assertTrue(result.issue_closed)
        self.assertTrue(any(command[:3] == ("gh", "pr", "checks") for command in runner.commands))
        self.assertTrue(any(command[:3] == ("gh", "pr", "merge") for command in runner.commands))
        self.assertTrue(any(command[:3] == ("gh", "issue", "view") for command in runner.commands))

    def test_finalize_promotes_existing_draft_pr_and_links_issue(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "harness" / "plans" / "issue-6-popular-menu-redis.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(manifest_bytes())
            runner = FakeRunner(
                pr_list=[
                    {
                        "number": 12,
                        "url": "https://github.com/beyejin/coffee-order-system/pull/12",
                        "isDraft": True,
                        "headRefOid": "a" * 40,
                        "body": "기존 초안 PR",
                    }
                ]
            )

            result = PUBLISH.finalize(
                root,
                Path("harness/plans/issue-6-popular-menu-redis.json"),
                runner=runner,
            )

        self.assertEqual("READY_FOR_REVIEW", result.state)
        self.assertEqual(12, result.pr_number)
        self.assertTrue(any(command[:3] == ("gh", "pr", "edit") for command in runner.commands))
        self.assertTrue(any(command[:3] == ("gh", "pr", "ready") for command in runner.commands))
        self.assertFalse(any(command[:3] == ("gh", "pr", "create") for command in runner.commands))

    def test_finalize_closes_open_issue_after_merge_when_needed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan_path = root / "harness" / "plans" / "issue-6-popular-menu-redis.json"
            plan_path.parent.mkdir(parents=True)
            plan_path.write_bytes(manifest_bytes())
            runner = FakeRunner(issue_state="OPEN")

            result = PUBLISH.finalize(
                root,
                Path("harness/plans/issue-6-popular-menu-redis.json"),
                merge=True,
                runner=runner,
            )

        self.assertTrue(result.issue_closed)
        self.assertTrue(any(command[:3] == ("gh", "issue", "close") for command in runner.commands))


if __name__ == "__main__":
    unittest.main()
