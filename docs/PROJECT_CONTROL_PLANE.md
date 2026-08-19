# Optional project control plane

A project and an experiment run solve different continuity problems.

## Project layer: why and what next

Use these files when work spans multiple bounded runs:

```text
project/
  PROJECT.md   # stable purpose, scope, constraints
  MEMORY.md    # current state only
  BACKLOG.md   # open work only
  ARCHIVE.md   # completed work and durable history
  runs/        # independent bounded-autoresearch runs
```

Copy the templates from `templates/project/` manually. The v0.2 CLI deliberately does not parse or mutate project planning files.

## Run layer: what was tested

Each child under `runs/` has its own frozen objective, metric, budget, event ledger, champion, findings, and results. Project notes are never copied into `events.jsonl`, are not evidence, and are not required for run validity.

## Lifecycle

1. Select one backlog item with a measurable empirical question.
2. Create a new bounded run under `runs/`.
3. Keep experiment evidence inside that run.
4. At termination, write only the concise decision/current state back to `MEMORY.md`.
5. Move completed backlog work to `ARCHIVE.md`; do not turn `MEMORY.md` into a historical log.

This separation prevents project-management context from being mistaken for experimental evidence.
