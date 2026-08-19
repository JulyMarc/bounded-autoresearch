"""Command-line interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core import checkpoint, init_run, record_experiment, repair_state_from_ledger, resume_data, resume_summary, validate_run


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="bounded-autoresearch")
    sub = root.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create a new bounded research run")
    init.add_argument("run_dir", type=Path)
    init.add_argument("--objective", required=True)
    init.add_argument("--metric", required=True)
    init.add_argument("--direction", choices=["minimize", "maximize"], required=True)
    init.add_argument("--max-experiments", type=int, default=6)
    init.add_argument("--wall-clock-minutes", type=int, default=120)
    init.add_argument("--compute-cap", default="No paid compute")
    validate = sub.add_parser("validate", help="Validate structural run and ledger invariants")
    validate.add_argument("run_dir", type=Path)
    validate.add_argument("--repair-state", action="store_true", help="Rebuild derived STATE.json from the canonical ledger")
    validate.add_argument("--json", action="store_true", dest="as_json")
    validate.add_argument("--public-safety", action="store_true", help="Also run the heuristic release scan")
    resume = sub.add_parser("resume", help="Validate and print the next action")
    resume.add_argument("run_dir", type=Path)
    resume.add_argument("--json", action="store_true", dest="as_json")
    record = sub.add_parser("record-experiment", help="Record one budget-consuming experiment attempt")
    record.add_argument("run_dir", type=Path)
    record.add_argument("--id", required=True, dest="experiment_id")
    record.add_argument("--outcome", choices=["success", "failed", "invalid"], required=True)
    record.add_argument("--metric-value", type=float)
    record.add_argument("--verified", action="store_true")
    record.add_argument("--prediction", required=True)
    record.add_argument("--gate", required=True)
    record.add_argument("--artifact")
    record.add_argument("--note", default="Experiment recorded")
    record.add_argument("--json", action="store_true", dest="as_json")
    point = sub.add_parser("checkpoint", help="Append a durable checkpoint")
    point.add_argument("run_dir", type=Path)
    point.add_argument("--status", choices=["running", "blocked"], required=True)
    point.add_argument("--next-action", required=True)
    point.add_argument("--note", default="Checkpoint")
    finish = sub.add_parser("finish", help="Close a run without performing external actions")
    finish.add_argument("run_dir", type=Path)
    finish.add_argument("--status", choices=["completed", "stopped"], required=True)
    finish.add_argument("--note", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "init":
            init_run(args.run_dir, objective=args.objective, metric=args.metric, direction=args.direction, max_experiments=args.max_experiments, wall_clock_minutes=args.wall_clock_minutes, compute_cap=args.compute_cap)
            print(f"Initialized {args.run_dir}")
        elif args.command == "validate":
            if args.repair_state:
                repair_state_from_ledger(args.run_dir)
            errors = validate_run(args.run_dir, scan_public_safety_patterns=args.public_safety)
            if args.as_json:
                print(json.dumps({"schema_version": 1, "ok": not errors, "errors": errors}, sort_keys=True))
            elif errors:
                print("INVALID")
                for error in errors:
                    print(f"- {error}")
            else:
                print("VALID")
            return 1 if errors else 0
        elif args.command == "resume":
            print(json.dumps(resume_data(args.run_dir), sort_keys=True) if args.as_json else resume_summary(args.run_dir))
        elif args.command == "record-experiment":
            result = record_experiment(
                args.run_dir, experiment_id=args.experiment_id, outcome=args.outcome,
                metric_value=args.metric_value, verified=args.verified,
                prediction=args.prediction, gate=args.gate, artifact=args.artifact, note=args.note,
            )
            print(json.dumps({"schema_version": 1, "ok": True, "experiment": result}, sort_keys=True) if args.as_json else f"Experiment {args.experiment_id} recorded; promoted={result['promoted']}")
        elif args.command == "checkpoint":
            checkpoint(args.run_dir, status=args.status, next_action=args.next_action, note=args.note)
            print("Checkpoint recorded")
        elif args.command == "finish":
            checkpoint(args.run_dir, status=args.status, next_action="No further action; run is terminal.", note=args.note)
            print(f"Run closed as {args.status}")
    except (FileExistsError, OSError, ValueError) as exc:
        as_json = getattr(args, "as_json", False)
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, sort_keys=True) if as_json else f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
