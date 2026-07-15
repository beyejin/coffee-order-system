from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORACLE_PATH = ROOT / "scripts/harness-oracles.py"
SPEC = importlib.util.spec_from_file_location("harness_oracles", ORACLE_PATH)
assert SPEC is not None and SPEC.loader is not None
ORACLES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ORACLES)


class OracleContractTest(unittest.TestCase):
    def test_all_eight_oracles_are_registered(self) -> None:
        self.assertEqual(8, len(ORACLES.ORACLE_IDS))
        self.assertEqual(set(ORACLES.ORACLE_IDS), set(ORACLES.GRADLE_TESTS) | {
            "oracle.architecture",
            "oracle.multi-instance",
        })

    def test_current_architecture_api_and_migration_contracts_pass(self) -> None:
        self.assertIn("architecture PASS", ORACLES.validate_architecture(ROOT))
        self.assertIn("api-contract PASS", ORACLES.validate_api_contract(ROOT))
        self.assertIn("migration sequence PASS", ORACLES.validate_migration_sequence(ROOT))

    def test_architecture_oracle_rejects_forbidden_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "harness/contracts").mkdir(parents=True)
            (root / "src/main/java/com/example/coffee/domain/order").mkdir(parents=True)
            (root / "src/main/java/com/example/coffee/domain/ranking").mkdir(parents=True)
            shutil.copy(
                ROOT / "harness/contracts/architecture.json",
                root / "harness/contracts/architecture.json",
            )
            (root / "src/main/java/com/example/coffee/domain/order/Bad.java").write_text(
                """package com.example.coffee.domain.order;

import com.example.coffee.domain.ranking.PopularMenu;

class Bad {}
""",
                encoding="utf-8",
            )
            (root / "src/main/java/com/example/coffee/domain/ranking/PopularMenu.java").write_text(
                "package com.example.coffee.domain.ranking;\nclass PopularMenu {}\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ORACLES.OracleFailure, "금지된 package 의존성"):
                ORACLES.validate_architecture(root)


if __name__ == "__main__":
    unittest.main()
