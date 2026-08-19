# Synthetic optimization example

This example is intentionally data-free. Initialize it with the README quick-start command, then compare a frozen constant baseline against one-variable changes to a deterministic toy function. Do not present the example as model research or benchmark evidence.

Suggested plan:

| ID | Hypothesis | One change | Gate |
|---|---|---|---|
| E00 | Establish deterministic baseline | none | repeated score is identical |
| E01 | Candidate A lowers the toy loss | parameter A only | score < baseline |
| E02 | Candidate B lowers the toy loss | parameter B only | score < verified champion |
