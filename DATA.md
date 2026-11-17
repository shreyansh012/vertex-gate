# Data

## What the demo and the tests use

Synthetic data only. `vertex_gate/toy.py` makes points with a seeded random
generator (y = 2x + 1 plus noise). Nothing is downloaded. The scores that come
out of it are toy numbers.

## What the pipeline file points at (not run here)

`pipeline/kfp_pipeline.py` reads one public BigQuery table:

- Table: `bigquery-public-data.samples.natality`
- Page that lists it: https://docs.cloud.google.com/bigquery/docs/sample-tables
  (the older cloud.google.com address redirects there)
- Google publishes the table as a BigQuery public dataset. The page describes
  it as all US births registered, 1969 to 2008.
- Licence of the page text: the page footer names the Creative Commons
  Attribution 4.0 licence. That covers the words on the page, not the rows.
- The licence of the rows themselves is not stated in this repo. Check the
  dataset entry in the BigQuery console.

No rows from this table are stored in this repo. The pipeline has never been
run here, so no data was fetched. The column names in its query
(`mother_age`, `gestation_weeks`, `plurality`, `weight_pounds`) were not
checked against the live table from this repo. Check them in the console
before you run it.
