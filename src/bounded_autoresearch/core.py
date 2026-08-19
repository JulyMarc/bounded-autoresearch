"""State and ledger operations for bounded research runs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
STATUSES = {"initialized", "running", "blocked", "completed", "stopped"}
TERMINAL_STATUSES = {"completed", "stopped"}
TRANSITIONS = {
    "initialized": {"running", "blocked", "stopped"},
    "running": {"running", "blocked", "completed", "stopped"},
    "blocked": {"running", "blocked", "completed", "stopped"},
    "completed": set(),
    "stopped": set(),
}
REQUIRED_FILES = {
    "TASK.md": "# Task\n\n## Objective\n{objective}\n\n## Metric\n{metric}\n",
    "BUDGET.md": "# Budget\n\nSee the frozen limits in `STATE.json`.\n",
    "PLAN.md": "# Experiment plan\n\n| ID | Hypothesis | One change | Prediction | Gate | Status |\n|---|---|---|---|---|---|\n",
    "FINDINGS.md": "# Findings\n\nRecord mechanisms, failures, and next levers.\n",
    "EXPERIMENTS.md": "# Experiments\n\n| ID | Change | Result | Verdict |\n|---|---|---|---|\n",
    "RESULTS.md": "# Results\n\nNot completed.\n",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


def dump_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def seal_event(event: dict[str, Any], previous_hash: str | None) -> dict[str, Any]:
    """Add a deterministic integrity hash chain; this detects corruption, not malicious rewriting."""
    sealed = {**event, "previous_hash": previous_hash}
    payload = json.dumps(sealed, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    sealed["event_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return sealed


def event_hash_is_valid(event: dict[str, Any], previous_hash: str | None) -> bool:
    claimed = event.get("event_hash")
    unsealed = {key: value for key, value in event.items() if key != "event_hash"}
    if unsealed.get("previous_hash") != previous_hash:
        return False
    payload = json.dumps(unsealed, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return claimed == hashlib.sha256(payload.encode("utf-8")).hexdigest()


@contextmanager
def run_lock(run_dir: Path):
    """Prevent concurrent writers and recover locks owned by absent local PIDs."""
    lock_path = run_dir / ".write.lock"
    if lock_path.exists():
        try:
            match = re.fullmatch(r"pid=(\d+)\n?", lock_path.read_text(encoding="ascii"))
        except (OSError, UnicodeError) as exc:
            raise ValueError(f"unreadable run lock: {lock_path}") from exc
        if not match:
            raise ValueError(f"malformed run lock: {lock_path}")
        pid = int(match.group(1))
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            lock_path.unlink()
        except PermissionError as exc:
            raise ValueError(f"run is locked by live or inaccessible pid {pid}") from exc
        else:
            raise ValueError(f"run is locked by live pid {pid}")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"run is locked by another writer: {lock_path}") from exc
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode())
        os.close(fd)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_events(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "events.jsonl"
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"events.jsonl:{line_number}: invalid JSON: {exc}") from exc
    return events


def write_events(run_dir: Path, events: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(event, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n" for event in events)
    atomic_write(run_dir / "events.jsonl", text)


def init_run(
    run_dir: Path,
    *,
    objective: str,
    metric: str,
    direction: str,
    max_experiments: int,
    wall_clock_minutes: int,
    compute_cap: str,
) -> dict[str, Any]:
    if run_dir.exists():
        raise FileExistsError(f"run already exists: {run_dir}")
    if not objective.strip() or not metric.strip():
        raise ValueError("objective and metric must be non-empty")
    if direction not in {"minimize", "maximize"}:
        raise ValueError("direction must be minimize or maximize")
    if max_experiments < 1 or wall_clock_minutes < 1:
        raise ValueError("budgets must be positive")
    run_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{run_dir.name}.init-", dir=run_dir.parent))
    timestamp = now()
    state = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid.uuid4()),
        "slug": run_dir.name,
        "status": "initialized",
        "objective": objective,
        "metric": {"name": metric, "direction": direction},
        "budget": {
            "max_experiments": max_experiments,
            "wall_clock_minutes": wall_clock_minutes,
            "compute_cap": compute_cap,
        },
        "experiments_attempted": 0,
        "no_improvement_epochs": 0,
        "champion": None,
        "next_action": "Research prior solutions and freeze the first experiment plan.",
        "pending_approvals": [],
        "created_at": timestamp,
        "updated_at": timestamp,
        "last_event_seq": 1,
    }
    event = seal_event({"schema_version": SCHEMA_VERSION, "seq": 1, "type": "initialized", "at": timestamp, "note": "Run initialized", "state": state}, None)
    try:
        write_events(staging, [event])
        atomic_write(staging / "STATE.json", dump_json(state))
        for name, template in REQUIRED_FILES.items():
            atomic_write(staging / name, template.format(objective=objective, metric=f"{metric} ({direction})"))
        (staging / "artifacts").mkdir()
        os.replace(staging, run_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return state


def checkpoint(run_dir: Path, *, status: str, next_action: str, note: str) -> dict[str, Any]:
    with run_lock(run_dir):
        errors = validate_run(run_dir)
        if errors:
            raise ValueError("invalid run: " + "; ".join(errors))
        events = load_events(run_dir)
        current = deepcopy(events[-1]["state"])
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        if status not in TRANSITIONS[current["status"]]:
            raise ValueError(f"invalid transition: {current['status']} -> {status}")
        if status == "completed" and current["experiments_attempted"] == 0:
            raise ValueError("empirical runs require at least one recorded attempt before completion")
        timestamp = now()
        current.update(status=status, next_action=next_action, updated_at=timestamp, last_event_seq=len(events) + 1)
        event = seal_event({"schema_version": SCHEMA_VERSION, "seq": len(events) + 1, "type": "checkpoint", "at": timestamp, "note": note, "state": current}, events[-1]["event_hash"])
        events.append(event)
        write_events(run_dir, events)
        atomic_write(run_dir / "STATE.json", dump_json(current))
        return current


def record_experiment(
    run_dir: Path,
    *,
    experiment_id: str,
    outcome: str,
    metric_value: float | None,
    verified: bool,
    prediction: str,
    gate: str,
    artifact: str | None,
    note: str,
) -> dict[str, Any]:
    """Record one budget-consuming attempt and promote verified improvements."""
    if not all(isinstance(value, str) and value.strip() for value in (experiment_id, prediction, gate)):
        raise ValueError("experiment id, prediction, and gate must be non-empty strings")
    if not isinstance(verified, bool):
        raise ValueError("verified must be a boolean")
    if outcome not in {"success", "failed", "invalid"}:
        raise ValueError("outcome must be success, failed, or invalid")
    if outcome == "success" and metric_value is None:
        raise ValueError("successful experiments require a metric value")
    if metric_value is not None and (not isinstance(metric_value, (int, float)) or isinstance(metric_value, bool) or not math.isfinite(metric_value)):
        raise ValueError("metric value must be a finite number")
    if outcome != "success" and metric_value is not None:
        raise ValueError("failed or invalid experiments cannot provide a metric value")
    if outcome != "success" and verified:
        raise ValueError("only successful experiments can be verified")
    if artifact and (Path(artifact).is_absolute() or ".." in Path(artifact).parts):
        raise ValueError("artifact must be a run-relative path without '..'")
    with run_lock(run_dir):
        errors = validate_run(run_dir)
        if errors:
            raise ValueError("invalid run: " + "; ".join(errors))
        events = load_events(run_dir)
        current = deepcopy(events[-1]["state"])
        if current["status"] not in {"running", "blocked"}:
            raise ValueError("experiments can only be recorded for running or blocked runs")
        existing_ids = {event.get("experiment", {}).get("id") for event in events}
        if experiment_id in existing_ids:
            raise ValueError(f"duplicate experiment id: {experiment_id}")
        attempted = current["experiments_attempted"]
        if attempted >= current["budget"]["max_experiments"]:
            raise ValueError("experiment budget exhausted")
        promoted = False
        if outcome == "success" and verified:
            champion = current.get("champion")
            direction = current["metric"]["direction"]
            promoted = champion is None or (metric_value < champion["metric_value"] if direction == "minimize" else metric_value > champion["metric_value"])
            if promoted:
                current["champion"] = {"experiment_id": experiment_id, "metric_value": metric_value, "verified": True}
                current["no_improvement_epochs"] = 0
            else:
                current["no_improvement_epochs"] += 1
        elif outcome != "invalid":
            current["no_improvement_epochs"] += 1
        timestamp = now()
        current.update(
            status="running",
            experiments_attempted=attempted + 1,
            next_action="Select the next bounded experiment or stop under the frozen rules.",
            updated_at=timestamp,
            last_event_seq=len(events) + 1,
        )
        experiment = {
            "id": experiment_id, "outcome": outcome, "metric_value": metric_value,
            "verified": verified, "promoted": promoted, "prediction": prediction,
            "gate": gate, "artifact": artifact,
        }
        event = seal_event({"schema_version": SCHEMA_VERSION, "seq": len(events) + 1, "type": "experiment_recorded", "at": timestamp, "note": note, "experiment": experiment, "state": current}, events[-1]["event_hash"])
        events.append(event)
        write_events(run_dir, events)
        atomic_write(run_dir / "STATE.json", dump_json(current))
        return experiment


def validate_ledger(events: list[dict[str, Any]]) -> list[str]:
    """Validate ledger invariants without trusting the derived STATE.json."""
    errors: list[str] = []
    if not events:
        return ["event ledger is empty"]
    first = events[0]
    initial = first.get("state")
    required_state = {
        "schema_version", "run_id", "slug", "status", "objective", "metric", "budget",
        "experiments_attempted", "no_improvement_epochs", "champion", "next_action",
        "pending_approvals", "created_at", "updated_at", "last_event_seq",
    }
    if first.get("type") != "initialized" or first.get("seq") != 1 or not isinstance(initial, dict):
        return ["ledger must start with a valid initialized event"]
    missing = sorted(required_state - initial.keys())
    if missing:
        return ["initial state missing fields: " + ", ".join(missing)]
    if initial.get("status") != "initialized" or initial.get("experiments_attempted") != 0 or initial.get("champion") is not None:
        errors.append("invalid initialized state")
    if initial.get("no_improvement_epochs") != 0 or initial.get("last_event_seq") != 1:
        errors.append("invalid initialized counters")
    metric = initial.get("metric", {})
    budget = initial.get("budget", {})
    if metric.get("direction") not in {"minimize", "maximize"} or not isinstance(metric.get("name"), str):
        errors.append("invalid metric contract")
    if not isinstance(budget.get("max_experiments"), int) or isinstance(budget.get("max_experiments"), bool) or budget.get("max_experiments", 0) < 1:
        errors.append("invalid experiment budget")
    if errors:
        return errors
    immutable = {key: deepcopy(initial.get(key)) for key in ("schema_version", "run_id", "slug", "objective", "metric", "budget", "created_at", "pending_approvals")}
    previous = deepcopy(initial)
    previous_hash: str | None = None
    seen_ids: set[str] = set()
    for index, event in enumerate(events, 1):
        event_state = event.get("state")
        if not event_hash_is_valid(event, previous_hash):
            errors.append(f"event hash chain mismatch at row {index}")
        previous_hash = event.get("event_hash") if isinstance(event.get("event_hash"), str) else None
        if event.get("seq") != index:
            errors.append(f"event sequence mismatch at row {index}")
        if event.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"unsupported event schema at row {index}")
        if event.get("type") not in {"initialized", "checkpoint", "experiment_recorded"}:
            errors.append(f"unknown event type at row {index}")
        if not isinstance(event_state, dict):
            errors.append(f"event row {index} has no state snapshot")
            continue
        missing = sorted(required_state - event_state.keys())
        if missing:
            errors.append(f"state row {index} missing fields: " + ", ".join(missing))
            continue
        for key, value in immutable.items():
            if event_state.get(key) != value:
                errors.append(f"immutable field {key} changed at row {index}")
        if event_state.get("last_event_seq") != index or event_state.get("updated_at") != event.get("at"):
            errors.append(f"state/event metadata mismatch at row {index}")
        if index == 1:
            previous = deepcopy(event_state)
            continue
        old_status = previous.get("status")
        new_status = event_state.get("status")
        if old_status not in TRANSITIONS or new_status not in TRANSITIONS[old_status]:
            errors.append(f"invalid ledger transition at row {index}: {old_status} -> {new_status}")
        expected = deepcopy(previous)
        expected.update(status=new_status, next_action=event_state.get("next_action"), updated_at=event.get("at"), last_event_seq=index)
        if event.get("type") == "checkpoint":
            if new_status == "completed" and previous.get("experiments_attempted") == 0:
                errors.append(f"completed empirical run has no attempts at row {index}")
        elif event.get("type") == "experiment_recorded":
            experiment = event.get("experiment")
            if not isinstance(experiment, dict):
                errors.append(f"missing experiment payload at row {index}")
                previous = deepcopy(event_state)
                continue
            experiment_id = experiment.get("id")
            outcome = experiment.get("outcome")
            value = experiment.get("metric_value")
            verified = experiment.get("verified")
            if not isinstance(experiment_id, str) or not experiment_id.strip() or experiment_id in seen_ids:
                errors.append(f"invalid or duplicate experiment id at row {index}")
            else:
                seen_ids.add(experiment_id)
            if outcome not in {"success", "failed", "invalid"}:
                errors.append(f"invalid experiment outcome at row {index}")
            if outcome == "success" and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)):
                errors.append(f"successful experiment has invalid metric at row {index}")
            if outcome != "success" and value is not None:
                errors.append(f"non-success experiment has a metric at row {index}")
            if not isinstance(verified, bool) or (verified and outcome != "success"):
                errors.append(f"invalid verification flag at row {index}")
            attempted = previous.get("experiments_attempted")
            if not isinstance(attempted, int) or attempted >= budget.get("max_experiments", 0):
                errors.append(f"experiment budget exceeded at row {index}")
                attempted = 0 if not isinstance(attempted, int) else attempted
            expected["experiments_attempted"] = attempted + 1
            expected["status"] = "running"
            expected["next_action"] = "Select the next bounded experiment or stop under the frozen rules."
            promoted = False
            if outcome == "success" and verified and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                champion = previous.get("champion")
                direction = metric["direction"]
                promoted = champion is None or (value < champion["metric_value"] if direction == "minimize" else value > champion["metric_value"])
                if promoted:
                    expected["champion"] = {"experiment_id": experiment_id, "metric_value": value, "verified": True}
                    expected["no_improvement_epochs"] = 0
                else:
                    expected["no_improvement_epochs"] = previous["no_improvement_epochs"] + 1
            elif outcome != "invalid":
                expected["no_improvement_epochs"] = previous["no_improvement_epochs"] + 1
            if experiment.get("promoted") is not promoted:
                errors.append(f"incorrect promotion flag at row {index}")
        else:
            errors.append(f"initialized event appears after row 1 at row {index}")
        if event_state != expected:
            errors.append(f"state snapshot is not derivable from event row {index}")
            return errors
        previous = deepcopy(event_state)
    return errors


def repair_state_from_ledger(run_dir: Path) -> None:
    """Recover derived state only from a fully valid canonical ledger."""
    with run_lock(run_dir):
        events = load_events(run_dir)
        errors = validate_ledger(events)
        if errors:
            raise ValueError("invalid canonical ledger: " + "; ".join(errors))
        atomic_write(run_dir / "STATE.json", dump_json(events[-1]["state"]))


def scan_public_safety(run_dir: Path) -> list[str]:
    """Run a heuristic release scan; this is not structural run validation."""
    errors: list[str] = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.name.endswith((".pyc", ".png", ".jpg", ".pdf")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                errors.append(f"public-safety pattern found in {path.relative_to(run_dir)}")
                break
    return errors


def validate_run(run_dir: Path, *, scan_public_safety_patterns: bool = False) -> list[str]:
    errors: list[str] = []
    if not run_dir.is_dir():
        return [f"run directory does not exist: {run_dir}"]
    for name in ["STATE.json", "events.jsonl", *REQUIRED_FILES]:
        if not (run_dir / name).is_file():
            errors.append(f"missing required file: {name}")
    if errors:
        return errors
    try:
        state = json.loads((run_dir / "STATE.json").read_text(encoding="utf-8"))
        events = load_events(run_dir)
    except (json.JSONDecodeError, ValueError) as exc:
        return [str(exc)]
    errors.extend(validate_ledger(events))
    if events and state != events[-1].get("state"):
        errors.append("STATE.json does not match the canonical last ledger event")
    if scan_public_safety_patterns:
        errors.extend(scan_public_safety(run_dir))
    return errors


def resume_data(run_dir: Path) -> dict[str, Any]:
    errors = validate_run(run_dir)
    if errors:
        raise ValueError("invalid run: " + "; ".join(errors))
    state = json.loads((run_dir / "STATE.json").read_text(encoding="utf-8"))
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": state["run_id"],
        "slug": state["slug"],
        "status": state["status"],
        "objective": state["objective"],
        "metric": state["metric"],
        "experiments_attempted": state["experiments_attempted"],
        "experiments_remaining": state["budget"]["max_experiments"] - state["experiments_attempted"],
        "champion": state["champion"],
        "next_action": state["next_action"],
    }


def resume_summary(run_dir: Path) -> str:
    data = resume_data(run_dir)
    return "\n".join([
        f"Run: {data['slug']} ({data['run_id']})",
        f"Status: {data['status']}",
        f"Objective: {data['objective']}",
        f"Metric: {data['metric']['name']} ({data['metric']['direction']})",
        f"Experiments remaining: {data['experiments_remaining']}",
        f"Next action: {data['next_action']}",
    ])
