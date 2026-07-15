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
                "HUMAN_REVIEW",
                "HUMAN_MERGE",
            ],
            self.policy["stateMachine"]["states"],
        )

    def test_main_and_merge_authority_are_separate(self) -> None:
        main = self.policy["mainOrchestrator"]
        merge_guard = self.policy["stateMachine"]["mergeGuard"]

        self.assertFalse(main["canWriteProductFiles"])
        self.assertFalse(main["canMerge"])
        self.assertEqual("user", main["mergeActor"])
        self.assertEqual("user", merge_guard["actor"])
        self.assertFalse(merge_guard["mainOrchestratorMayMerge"])
        self.assertEqual(
            ["HUMAN_REVIEW"],
            self.policy["stateMachine"]["nonMergeTerminalStates"],
        )

    def test_exhausted_repair_loop_stops_for_human_review(self) -> None:
        transitions = self.policy["stateMachine"]["transitions"]

        self.assertEqual("HUMAN_REVIEW", transitions["FAIL"]["exhaustedTo"])
        self.assertEqual(
            "HUMAN_REVIEW",
            next(
                transition["to"]
                for transition in transitions["repair"]
                if transition["from"] == "FIX_LOOP"
                and transition["to"] == "HUMAN_REVIEW"
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
