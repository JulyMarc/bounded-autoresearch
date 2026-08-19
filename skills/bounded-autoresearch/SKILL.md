---
name: bounded-autoresearch
description: Initialize, run, checkpoint, resume, and close bounded empirical research with explicit metrics, budgets, stopping rules, durable ledgers, and human approval gates.
---

# Bounded Autoresearch

Use this skill for empirical optimization, ablations, benchmark comparisons, reproduction attempts, and feasibility studies that may require multiple experiments.

## Router

1. If no `STATE.json` exists, follow `../../workflows/start.md`.
2. If `STATE.json` exists, validate it before doing work and follow `../../workflows/resume.md`.
3. If status is `completed` or `stopped`, do not restart or overwrite the run. Create a new run with a new research contract.

## Invariants

- Research existing solutions before meaningful compute.
- Freeze objective, metric, data boundary, budget, and stopping rules.
- Change one experimental variable at a time unless a structural experiment explicitly requires a bundle.
- Record failures and mechanisms, not only winners.
- Keep holdout data outside iterative tuning.
- Verify a candidate before replacing the champion.
- Never fabricate unavailable metrics.
- External, destructive, privileged, or paid actions require explicit human approval.
- A completed workflow does not establish scientific validity by itself.
