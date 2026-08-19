# Start workflow

1. State the exact objective and metric direction.
2. Record unknowns and inspect prior solutions before requesting avoidable details.
3. Freeze data/evaluation boundaries and forbidden holdout tuning.
4. Record experiment, wall-clock, compute/API-money, retry, and no-improvement limits.
5. Record actions requiring human approval.
6. Initialize the run exactly once. Never initialize over an existing directory.
7. Populate `TASK.md`, `BUDGET.md`, and the first diverse hypotheses in `PLAN.md`.
8. Validate before running meaningful compute.

A start is complete only when another session can understand the objective, limits, baseline plan, and next action from disk.
