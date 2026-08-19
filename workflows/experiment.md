# Experiment workflow

For each experiment:

1. Write the hypothesis, single change, mechanism, prediction, and gate before execution.
2. Reject near-duplicates, leakage-prone ideas, and changes to the wrong component.
3. Execute within the frozen budget and save the exact command/environment.
4. Use `record-experiment`; every recorded attempt consumes one experiment slot, including failures and invalid runs.
5. Use a unique experiment ID. Successful outcomes require a numeric metric; failed/invalid outcomes must not invent one.
6. Mark `--verified` only after the declared gate passes. Only a verified directional improvement can replace the champion.
7. Record artifacts as run-relative paths and write failure autopsies in `FINDINGS.md`.
8. Checkpoint the next action. Never infer success from process completion alone.
