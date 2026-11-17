# Khiops DuckDB

[![CI](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml/badge.svg)](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml)
[![Docs](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/docs.yaml/badge.svg)](https://khiopslab.github.io/khiops-duckdb/)
[![Release](https://img.shields.io/github/v/release/KhiopsLab/khiops-duckdb?include_prereleases)](https://github.com/KhiopsLab/khiops-duckdb/releases)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-BSD--3--Clause--Clear-blue)](LICENSE)

**Run Khiops on any data DuckDB can read.**

Parquet, CSV, JSON, SQL databases, BigQuery, cloud buckets, DataFrames: if DuckDB
can query it, Khiops can learn from it. Filter and join in SQL, then train. No
export script to write, no pandas copy of your data.

```bash
uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"
```

## Use

```python
import duckdb
import khiops.core as kh
from khiops_duckdb import build_dictionary_from_relation, export_data_table

customers = duckdb.sql("FROM 'customers.parquet'")   # any DuckDB source

dictionary_domain = build_dictionary_from_relation(
    customers, "Customer", output_dictionary_file_path="customer.kdic",
)
data_table_path = export_data_table(
    customers, "customers.tsv", dictionary_domain, "Customer",
)

report, model = kh.train_predictor(
    dictionary_domain, "Customer", data_table_path, "churn", "results/report.khj",
)
kh.deploy_model(model, "SNB_Customer", data_table_path, "results/scores.tsv")
```

Two functions, then plain `khiops.core`:

- `build_dictionary_from_relation` drafts the Khiops dictionary from the
  schema and saves it. On later runs it keeps the file, so you can adjust it
  by hand.
- `export_data_table` writes the data table that dictionary describes: only
  its columns, in its date formats, sorted by its key as Khiops requires.

For BigQuery, install `khiops-duckdb[gcp]` and start from
`read_bigquery("SELECT ...")`; no DuckDB extension is needed.

The [documentation](https://khiopslab.github.io/khiops-duckdb/) covers
[data sources](https://khiopslab.github.io/khiops-duckdb/sources.html),
[the dictionary file](https://khiopslab.github.io/khiops-duckdb/dictionary.html),
[multiple tables](https://khiopslab.github.io/khiops-duckdb/multitable.html) and
the [export format](https://khiopslab.github.io/khiops-duckdb/semantics.html).

## Develop

```bash
uv sync --group dev
uv run pytest
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

On Windows, expose Khiops' installed MPI DLLs before running the engine:
``$env:PATH = "$(Resolve-Path .venv/Library/bin);$env:PATH"`` (PowerShell).
This is needed for serial execution on low-core machines with Khiops 11.

## License

[BSD 3-Clause Clear](LICENSE).
