# vertex-gate

A model deploy gate that fails closed. A new model version goes live only if
its score beats the live version by a set margin. If the score of a later
version is missing, NaN or malformed, or the gate cannot run, the answer is
"block". The very first version deploys with no comparison (see DECISIONS.md,
entry 4).

## What this demo shows

It shows a small registry file, a gate that decides deploy or block, and an
audit log that records every decision before anything changes. The core is
plain Python and runs offline with no account. It also includes a Kubeflow
Pipelines definition (preprocess, train, evaluate, gate, deploy) that is
**NOT RUN** in this repo, because it needs a Google Cloud project.

## How to run it

You need Python 3.11 or newer. Nothing else to install.

```
python -m unittest discover -s tests -v
python -m vertex_gate demo
python -m vertex_gate selftest
```

The demo writes `demo_out/registry.json` and `demo_out/audit.jsonl`. It
refuses to run if either file already exists in its output folder. Add
`--force` to overwrite them: `python -m vertex_gate demo --dir demo_out --force`.
The
self-test plants bad scores (NaN, infinity, text, true/false, none, a list)
and exits with code 0 only if the gate rejected every one.

To gate your own versions:

```
python -m vertex_gate register my_registry.json v1 --metric rmse=2.0
python -m vertex_gate register my_registry.json v2 --metric rmse=1.5
python -m vertex_gate gate my_registry.json v1 --audit audit.jsonl
python -m vertex_gate gate my_registry.json v2 --audit audit.jsonl --margin 0.1
```

`gate` exits 0 if the version was deployed and 1 if it was blocked. Use
`--higher-is-better` for scores where bigger is better. `register` creates the
registry file only if it does not exist. If the file exists but is damaged, it
prints an error, exits with code 2 and leaves the file alone.

## The rules

1. The first version always deploys (nothing is live to compare with).
2. Later versions must beat the live one by more than the margin. A tie is a block.
3. Missing, NaN, infinite or non-number scores are a block, except for the first version (rule 1).
4. If the gate cannot run (bad config, broken registry, cannot write the log), that is a block.
5. The audit line is written before the registry changes.

Reasons for each choice are in [DECISIONS.md](DECISIONS.md). Data sources are
in [DATA.md](DATA.md).

## The pipeline file

`pipeline/kfp_pipeline.py` wires the five stages for a linear regression on
the public BigQuery table `bigquery-public-data.samples.natality`. It is a
sketch. It has not been compiled or run here. Its `has_current` and
`current_rmse` inputs have no defaults: leave them out and the run fails
instead of deploying. kfp is an optional import, so
the tests do not need it. To try it yourself you would run
`pip install kfp` and use your own Google Cloud project.

## What it does NOT prove

- It does not prove any model is good. The models here are toy numbers on
  made-up data. Treat the scores as labels, not results.
- It does not prove the Kubeflow pipeline works. Nobody ran it here.
- It does not prove the gate is safe against a person who edits the registry
  or the log by hand. Both are plain files with no signing and no access control.
- A margin on one metric is a thin check. It does not look at fairness,
  drift, latency or cost, and it does not use confidence intervals.
- The "deploy" here only changes a field in a JSON file. It does not serve a model.
- It has no file locking. Two gates running at once on one registry can overwrite each other.
- The registry is replaced by rename without an fsync of the temp file, so a power cut may lose or empty it.
- If the first version has a bad score, later versions stay blocked until
  someone repairs the registry (see DECISIONS.md, entry 4).

## Layout

```
vertex_gate/   registry, gate, audit log, toy models, demo, self-test, CLI
pipeline/      kfp v2 pipeline sketch (not run)
tests/         unittest tests
```

AI-assisted, with tests and review gates.

## Licence

MIT. See [LICENSE](LICENSE).
