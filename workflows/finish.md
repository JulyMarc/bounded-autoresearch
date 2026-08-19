# Finish workflow

Close as `completed` only when the declared output and verification gate are satisfied. Close as `stopped` when budget, blocker, invalid design, or stop rule ends the run.

`RESULTS.md` must state:
- champion or “baseline stands”;
- comparison and reproduction command;
- used budget;
- failures and negative results;
- caveats and claim boundary;
- any deviations from the frozen contract.

Terminal states are irreversible. A follow-up requires a new run.
