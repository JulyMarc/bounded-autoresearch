# Bounded Autoresearch

A provider-neutral control plane for bounded, resumable empirical research.

Bounded Autoresearch gives agents and human operators a durable run contract, a replay-validated event ledger, explicit experiment budgets, and a predictable resume point. It is local-first, has no runtime dependencies, and does not execute compute or external actions.

## Key capabilities

- **Bounded runs** — freeze the objective, metric direction, and experiment-count budget.
- **Agent-friendly CLI** — initialize, validate, checkpoint, record experiments, resume, and finish.
- **Durable state** — canonical `events.jsonl` plus derived `STATE.json`.
- **Ledger integrity** — SHA-256 event chain and deterministic invariant replay before repair.
- **Verified champion promotion** — only finite, successful, verified directional improvements replace the current champion.
- **Safe continuation** — atomic file replacement, per-run writer lock, stale local-PID recovery, and irreversible terminal states.
- **Structured output** — JSON responses for agent integrations.
- **Project continuity templates** — optional separation of project backlog/memory from experimental evidence.

## Scope

The CLI manages research state; it does not run training jobs, access networks, spend money, modify production systems, or perform destructive actions. Experiment-count budgets are enforced in code. Wall-clock and compute accounting, holdout discipline, approvals, and scientific-quality decisions remain operator responsibilities.

## Requirements

- Python 3.10+
- No runtime dependencies

## Quick start

Run directly from a clone:

```bash
PYTHONPATH=src python3 -m bounded_autoresearch.cli init runs/demo \
  --objective "Reduce synthetic validation error" \
  --metric validation_error \
  --direction minimize \
  --max-experiments 6 \
  --wall-clock-minutes 120

PYTHONPATH=src python3 -m bounded_autoresearch.cli checkpoint runs/demo \
  --status running \
  --next-action "Run the frozen baseline" \
  --note "Prior-solution scan complete"

PYTHONPATH=src python3 -m bounded_autoresearch.cli record-experiment runs/demo \
  --id E00 \
  --outcome success \
  --metric-value 0.42 \
  --verified \
  --prediction "The baseline is deterministic" \
  --gate "Repeated evaluation matches"

PYTHONPATH=src python3 -m bounded_autoresearch.cli resume runs/demo --json
```

Close a run explicitly:

```bash
PYTHONPATH=src python3 -m bounded_autoresearch.cli finish runs/demo \
  --status stopped \
  --note "Budget exhausted; baseline stands"
```

## Run structure

```text
runs/demo/
├── STATE.json          # derived current state
├── events.jsonl        # canonical hash-chained event ledger
├── TASK.md
├── BUDGET.md
├── PLAN.md
├── FINDINGS.md
├── EXPERIMENTS.md
├── RESULTS.md
└── artifacts/
```

`init` never overwrites an existing directory. Every recorded attempt consumes one experiment slot, including failed and invalid attempts. Terminal runs cannot be reopened.

## Validation and recovery

Structural validation checks state transitions, immutable run fields, unique experiment IDs, budget counters, metric contracts, champion provenance, promotion direction, and the event hash chain.

```bash
PYTHONPATH=src python3 -m bounded_autoresearch.cli validate runs/demo
```

If a process stops after the ledger update but before the derived state update, rebuild `STATE.json` only after validating the canonical ledger:

```bash
PYTHONPATH=src python3 -m bounded_autoresearch.cli validate runs/demo --repair-state
```

The optional publication heuristic is intentionally separate from run validity:

```bash
PYTHONPATH=src python3 -m bounded_autoresearch.cli validate runs/demo --public-safety
```

The event hash chain detects accidental or uncoordinated modification. It is not a digital signature or WORM storage guarantee.

## Workflow resources

- [`skills/bounded-autoresearch/SKILL.md`](skills/bounded-autoresearch/SKILL.md)
- [`workflows/start.md`](workflows/start.md)
- [`workflows/resume.md`](workflows/resume.md)
- [`workflows/experiment.md`](workflows/experiment.md)
- [`workflows/finish.md`](workflows/finish.md)
- [`policies/experiment-decision.md`](policies/experiment-decision.md)
- [`docs/PROJECT_CONTROL_PLANE.md`](docs/PROJECT_CONTROL_PLANE.md)

The optional project layer keeps `PROJECT.md`, `MEMORY.md`, `BACKLOG.md`, and `ARCHIVE.md` outside run evidence. Each empirical question receives an independent child run.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m pip wheel . --no-build-isolation --no-deps --wheel-dir dist
```

GitHub Actions run the same test and package-build gates.

## Evidence boundary

A valid ledger proves that the recorded workflow is internally consistent. It does not establish that a dataset, benchmark, causal claim, model comparison, or scientific conclusion is valid. Independent evaluation and domain review remain necessary.

## License

Apache-2.0.
