from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "harness" / "orchestration-policy.json"


class OrchestrationPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))

    def test_role_slots_are_fixed(self) -> None:
        slots = self.policy["roleSlots"]

        self.assertTrue(self.policy["scope"]["oneBranchPerIssue"])
        self.assertTrue(self.policy["scope"]["onePrPerIssue"])
        self.assertEqual(4, slots["maxPerIssue"])
        self.assertEqual(2, slots["maxConcurrent"])
        self.assertIn("shared DB", slots["parallelCondition"])
        self.assertEqual(
            ["implementation", "verification", "qa", "pr-review"],
            slots["roles"],
        )

    def test_only_implementation_can_write(self) -> None:
        roles = self.policy["roles"]

        self.assertTrue(roles["implementation"]["writer"])
        self.assertFalse(roles["implementation"]["readOnly"])
        for role in ("verification", "qa", "pr-review"):
            self.assertFalse(roles[role]["writer"])
            self.assertTrue(roles[role]["readOnly"])
            self.assertEqual("none", roles[role]["writeScope"])

    def test_vcs_capability_matrix_is_explicit(self) -> None:
        expected = {
            "implementation": {
                "read": True,
                "writeProductFiles": True,
                "writeScope": "manifest.allowedPaths",
                "commit": True,
                "push": False,
                "merge": False,
            },
            "verification": {
                "read": True,
                "writeProductFiles": False,
                "writeScope": "none",
                "commit": False,
                "push": False,
                "merge": False,
            },
            "qa": {
                "read": True,
                "writeProductFiles": False,
                "writeScope": "none",
                "commit": False,
                "push": False,
                "merge": False,
            },
            "pr-review": {
                "read": True,
                "writeProductFiles": False,
                "writeScope": "none",
                "commit": False,
                "push": False,
                "merge": False,
            },
            "main-orchestrator": {
                "read": True,
                "writeProductFiles": False,
                "writeScope": "none",
                "commit": False,
                "push": True,
                "merge": True,
            },
        }
        assert self.policy["vcsCapabilities"] == expected

    def test_limits_and_state_machine_are_explicit(self) -> None:
        self.assertEqual(
            {
                "maxRepairLoops": 3,
                "maxPrReviewRereviews": 2,
                "maxWritersPerIssue": 1,
            },
            self.policy["limits"],
        )
        self.assertEqual(
            [
                "PLAN",
                "ASSIGN",
                "IMPLEMENT",
                "VERIFY",
                "QA",
                "PR_REVIEW",
                "FIX_LOOP",
                "FINAL_EVALUATE",
                "FAILED",
                "AUTO_MERGE",
            ],
            self.policy["stateMachine"]["states"],
        )
        self.assertNotIn("HUMAN_REVIEW", self.policy["stateMachine"]["states"])
        self.assertNotIn("HUMAN_MERGE", self.policy["stateMachine"]["states"])

    def test_main_orchestrator_owns_automatic_merge(self) -> None:
        main = self.policy["mainOrchestrator"]
        merge_guard = self.policy["stateMachine"]["mergeGuard"]

        self.assertTrue(self.policy["scope"]["externalServices"])
        self.assertFalse(main["canWriteProductFiles"])
        self.assertTrue(main["canMerge"])
        self.assertEqual("main-orchestrator", main["mergeActor"])
        self.assertEqual("scripts/agent-publish.py", main["providerRuntime"])
        self.assertEqual("main-orchestrator", merge_guard["actor"])
        self.assertTrue(merge_guard["mainOrchestratorMayMerge"])
        self.assertEqual(
            ["FAILED"],
            self.policy["stateMachine"]["nonMergeTerminalStates"],
        )
        self.assertNotIn("MERGE", main["mustNotPerform"])

    def test_exhausted_repair_loop_stops_without_merge(self) -> None:
        transitions = self.policy["stateMachine"]["transitions"]

        self.assertEqual("FAILED", transitions["FAIL"]["exhaustedTo"])
        self.assertEqual(
            "FAILED",
            next(
                transition["to"]
                for transition in transitions["repair"]
                if transition["from"] == "FIX_LOOP"
                and transition["to"] == "FAILED"
            ),
        )

    def test_single_source_and_handoff_contract_are_fixed(self) -> None:
        self.assertEqual(
            [
                "manifest",
                "candidateHead",
                "allowedPaths",
                "completionContract",
                "handoffSchema",
            ],
            self.policy["singleSourceOfTruth"]["items"],
        )
        self.assertEqual(
            [
                "role",
                "candidateHead",
                "issue",
                "status",
                "changedPaths",
                "commands",
                "evidence",
                "findings",
                "nextAction",
                "manifest",
                "allowedPaths",
                "completionContract",
                "state",
                "nextState",
            ],
            self.policy["handoffSchema"]["requiredFields"],
        )

    def test_reviewers_are_read_only_and_reject_requires_findings(self) -> None:
        review = self.policy["reviewContract"]

        self.assertEqual(
            ["verification", "qa", "pr-review"],
            review["reviewerRoles"],
        )
        self.assertTrue(review["readOnly"])
        self.assertFalse(review["canModifyCodeOrDocs"])
        self.assertTrue(review["rejectRequiresBlockingFindings"])
        self.assertTrue(review["mainMustRerunFinalEvaluate"])


if __name__ == "__main__":
    unittest.main()
