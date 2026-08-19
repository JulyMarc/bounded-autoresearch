from __future__ import annotations

import json
import tempfile
from copy import deepcopy
import unittest
from pathlib import Path

from bounded_autoresearch.core import checkpoint, init_run, record_experiment, repair_state_from_ledger, resume_data, resume_summary, seal_event, validate_ledger, validate_run


class RunTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.run = Path(self.temp.name) / "demo"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def initialize(self) -> None:
        init_run(
            self.run,
            objective="Reduce synthetic error",
            metric="validation_error",
            direction="minimize",
            max_experiments=4,
            wall_clock_minutes=30,
            compute_cap="No paid compute",
        )

    def test_init_creates_valid_run(self) -> None:
        self.initialize()
        self.assertEqual(validate_run(self.run), [])
        state = json.loads((self.run / "STATE.json").read_text())
        self.assertEqual(state["status"], "initialized")
        self.assertEqual(state["last_event_seq"], 1)

    def test_init_never_overwrites(self) -> None:
        self.initialize()
        original = (self.run / "STATE.json").read_text()
        with self.assertRaises(FileExistsError):
            self.initialize()
        self.assertEqual((self.run / "STATE.json").read_text(), original)

    def test_checkpoint_and_resume(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Run E00", note="Plan frozen")
        self.assertEqual(validate_run(self.run), [])
        summary = resume_summary(self.run)
        self.assertIn("Status: running", summary)
        self.assertIn("Next action: Run E00", summary)

    def test_terminal_state_is_irreversible(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Verify", note="Started")
        record_experiment(
            self.run, experiment_id="E00", outcome="failed", metric_value=None,
            verified=False, prediction="probe", gate="recorded", artifact=None, note="Attempt",
        )
        checkpoint(self.run, status="completed", next_action="None", note="Done")
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            checkpoint(self.run, status="running", next_action="Restart", note="Unsafe")

    def test_detects_and_repairs_state_ledger_mismatch(self) -> None:
        self.initialize()
        state = json.loads((self.run / "STATE.json").read_text())
        state["next_action"] = "Tampered"
        (self.run / "STATE.json").write_text(json.dumps(state))
        self.assertTrue(any("canonical" in error for error in validate_run(self.run)))
        repair_state_from_ledger(self.run)
        self.assertEqual(validate_run(self.run), [])

    def test_cannot_complete_before_recorded_attempt(self) -> None:
        self.initialize()
        with self.assertRaisesRegex(ValueError, "invalid transition"):
            checkpoint(self.run, status="completed", next_action="None", note="Premature")
        checkpoint(self.run, status="running", next_action="Run", note="Started")
        with self.assertRaisesRegex(ValueError, "at least one"):
            checkpoint(self.run, status="completed", next_action="None", note="Still premature")

    def test_rejects_malformed_writer_lock(self) -> None:
        self.initialize()
        (self.run / ".write.lock").write_text("held")
        with self.assertRaisesRegex(ValueError, "malformed"):
            checkpoint(self.run, status="running", next_action="Wait", note="Conflict")

    def test_recovers_absent_pid_lock(self) -> None:
        self.initialize()
        (self.run / ".write.lock").write_text("pid=99999999\n")
        checkpoint(self.run, status="running", next_action="Continue", note="Recovered")
        self.assertFalse((self.run / ".write.lock").exists())

    def test_agent_experiment_lifecycle_and_budget(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Run E00", note="Started")
        first = record_experiment(
            self.run, experiment_id="E00", outcome="success", metric_value=1.0,
            verified=True, prediction="baseline is deterministic", gate="repeat matches",
            artifact="artifacts/e00.json", note="Baseline",
        )
        self.assertTrue(first["promoted"])
        second = record_experiment(
            self.run, experiment_id="E01", outcome="success", metric_value=0.8,
            verified=True, prediction="change lowers error", gate="value < 1.0",
            artifact=None, note="Improvement",
        )
        self.assertTrue(second["promoted"])
        third = record_experiment(
            self.run, experiment_id="E02", outcome="success", metric_value=0.9,
            verified=True, prediction="change lowers error", gate="value < 0.8",
            artifact=None, note="Regression",
        )
        self.assertFalse(third["promoted"])
        data = resume_data(self.run)
        self.assertEqual(data["experiments_attempted"], 3)
        self.assertEqual(data["champion"]["experiment_id"], "E01")

    def test_validator_returns_errors_for_poisoned_intermediate_state(self) -> None:
        self.initialize()
        events = [json.loads(line) for line in (self.run / "events.jsonl").read_text().splitlines()]
        initial = events[0]["state"]
        poisoned = deepcopy(initial)
        poisoned.update(status="running", updated_at="t2", last_event_seq=2, champion="poison")
        second = seal_event(
            {"schema_version": 1, "seq": 2, "type": "checkpoint", "at": "t2", "note": "bad", "state": poisoned},
            events[0]["event_hash"],
        )
        later = deepcopy(poisoned)
        later.update(updated_at="t3", last_event_seq=3, experiments_attempted=1)
        third = seal_event(
            {"schema_version": 1, "seq": 3, "type": "experiment_recorded", "at": "t3", "note": "later", "experiment": {"id": "E00", "outcome": "success", "metric_value": 1.0, "verified": True, "promoted": False, "prediction": "p", "gate": "g", "artifact": None}, "state": later},
            second["event_hash"],
        )
        errors = validate_ledger([events[0], second, third])
        self.assertTrue(any("not derivable" in error for error in errors))

    def test_repair_rejects_tampered_ledger(self) -> None:
        self.initialize()
        events_path = self.run / "events.jsonl"
        events = [json.loads(line) for line in events_path.read_text().splitlines()]
        events[-1]["state"]["objective"] = "tampered"
        events_path.write_text("".join(json.dumps(event) + "\n" for event in events))
        with self.assertRaisesRegex(ValueError, "event hash chain mismatch"):
            repair_state_from_ledger(self.run)

    def test_failed_experiment_cannot_be_verified(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Run", note="Started")
        with self.assertRaisesRegex(ValueError, "only successful"):
            record_experiment(
                self.run, experiment_id="E00", outcome="failed", metric_value=None,
                verified=True, prediction="probe", gate="fails", artifact=None, note="Invalid",
            )

    def test_non_finite_metric_is_rejected(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Run", note="Started")
        with self.assertRaisesRegex(ValueError, "finite"):
            record_experiment(
                self.run, experiment_id="E00", outcome="success", metric_value=float("nan"),
                verified=True, prediction="test", gate="finite", artifact=None, note="Invalid metric",
            )

    def test_duplicate_id_and_budget_are_rejected(self) -> None:
        self.initialize()
        checkpoint(self.run, status="running", next_action="Run", note="Started")
        kwargs = dict(outcome="failed", metric_value=None, verified=False, prediction="test", gate="no crash", artifact=None, note="Attempt")
        record_experiment(self.run, experiment_id="E00", **kwargs)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            record_experiment(self.run, experiment_id="E00", **kwargs)
        for index in range(1, 4):
            record_experiment(self.run, experiment_id=f"E{index:02d}", **kwargs)
        with self.assertRaisesRegex(ValueError, "budget exhausted"):
            record_experiment(self.run, experiment_id="E04", **kwargs)

    def test_public_safety_scan_is_separate_from_run_validity(self) -> None:
        self.initialize()
        (self.run / "FINDINGS.md").write_text("artifact: /home/example/private/result.json\n")
        self.assertEqual(validate_run(self.run), [])
        self.assertTrue(any("public-safety" in error for error in validate_run(self.run, scan_public_safety_patterns=True)))
        checkpoint(self.run, status="running", next_action="Continue", note="Local paths are allowed")

    def test_rejects_invalid_budget(self) -> None:
        with self.assertRaisesRegex(ValueError, "budgets must be positive"):
            init_run(
                self.run,
                objective="Test",
                metric="score",
                direction="maximize",
                max_experiments=0,
                wall_clock_minutes=10,
                compute_cap="None",
            )


if __name__ == "__main__":
    unittest.main()
