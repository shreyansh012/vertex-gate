# Decision log

Each entry: the decision, why, and the option I turned down.

## 1. Fail closed

- Decision: if anything is missing, odd or broken, the gate says "block".
  This covers a missing metric, NaN, infinity, text, a true/false value, a
  bad config, a corrupt registry file and any unexpected error.
- Why: a wrong block costs a re-run. A wrong deploy puts a bad model in use.
- Rejected: "allow if unsure". It is quicker to build but it hides bugs.

## 2. A tie is a block

- Decision: the candidate must beat the deployed version by MORE than the
  margin. Equal scores, and a gain exactly equal to the margin, are blocked.
- Why: a deploy has a cost and a risk. No measured gain means no reason to
  pay it.
- Rejected: "at least as good". It would redeploy the same model again and again.

## 3. Audit line first, deploy second

- Decision: the decision is written and flushed to disk before the registry
  changes. If the write fails, the answer is "block" and nothing deploys.
- Why: a deploy with no record is worse than no deploy.
- Rejected: deploy first, then log. A crash in between leaves a silent deploy.

## 4. The first version always deploys

- Decision: when nothing is deployed, the first version deploys, as the
  brief for this demo says. If its metric is bad, the audit line carries a
  warning.
- Why: there is nothing to compare against.
- Rejected: demand a valid metric even for the first version. It is safer,
  but it breaks the stated rule. Cost of my choice: a first version with a
  bad metric blocks every later version (the deployed metric is unusable)
  until someone fixes the registry by hand.

## 5. Plain JSON file for the registry, JSON lines for the audit log

- Decision: both are text files. The registry is saved by writing a temp file
  and renaming it. The audit log only ever appends.
- Why: no server, no account, easy to read, works on Windows and Linux.
- Rejected: SQLite. It is fine, but a text file shows the idea with less code
  and can be read in any editor.

## 6. Reason codes instead of free text

- Decision: every decision has a short code such as `NO_IMPROVEMENT` or
  `METRIC_INVALID`, plus a detail sentence.
- Why: tests and log readers can match on the code.
- Rejected: free text only. It is hard to test and to search.

## 7. Booleans are not numbers

- Decision: `True` and `False` are rejected as metrics.
- Why: in Python `True == 1`, so a stray flag could pass as a score of 1.
- Rejected: accept any `int` or `float` as it is.

## 8a. Safety rules for the command line

- Decision: `register` starts a new registry only when the file does not
  exist. A damaged file is an error (exit 2) and is never overwritten. `demo`
  refuses to touch an existing `registry.json` or `audit.jsonl` unless
  `--force` is given.
- Why: a quiet reset of a damaged registry would clear the "deployed" field
  and let the next version deploy as a first version. A demo must not delete
  a real audit log.
- Rejected: treat any read error as "new registry". It hides damage.

## 8. kfp is optional, and the pipeline file is not run

- Decision: `pipeline/kfp_pipeline.py` imports kfp inside a `try`. The tests
  never need it. The file is marked NOT RUN in its header and in the README.
- Why: running it needs a Google Cloud project and billing. I will not claim
  a result I did not get.
- Rejected: add kfp as a hard requirement. It is a large install that the
  gate itself does not need.

## 9. A small copy of the rule inside the pipeline file

- Decision: `gate_decision()` in the pipeline file repeats the rule in
  plain Python. A test runs both on 100 input combinations and checks they
  agree.
- Why: a pipeline step runs in its own container and cannot import this repo.
- Rejected: one shared module. It would need a package build and a registry
  to host it, which is out of scope for a demo.

## 10. Toy models on made-up data for the demo

- Decision: the demo compares a "predict the average" model with a straight
  line fit, on random data from a fixed seed. One version is a copy of the
  other (to show a tie).
- Why: it runs offline in under a second and the outcome is the same on every
  run.
- Rejected: download the public table. It needs an account and the network,
  and the demo is about the gate, not the model.
