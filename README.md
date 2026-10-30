# Khiops DuckDB

[![CI](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml/badge.svg)](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml)
[![Docs](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/docs.yaml/badge.svg)](https://khiopslab.github.io/khiops-duckdb/)
[![Release](https://img.shields.io/github/v/release/KhiopsLab/khiops-duckdb?include_prereleases)](https://github.com/KhiopsLab/khiops-duckdb/releases)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-BSD--3--Clause--Clear-blue)](LICENSE)

**From Parquet or SQL to a trained Khiops model in one call.**

Point Khiops at your data, choose a target, and get a model and report.
No manual TSV export or Khiops dictionary setup for ordinary scalar data.

## Why use it?

- **Less data plumbing.** Read Parquet, CSV, JSON or a DuckDB query through the
  same API. Schema inference and temporary files are handled for you.
- **No full pandas copy.** Core tasks stream through local snapshots instead of
  collecting the entire dataset into a DataFrame.
- **Related tables, not manual flattening.** Declare customer/order keys and let
  Khiops construct features from the relationships.
- **Your workflow stays yours.** Reuse your DuckDB connection for SQL, databases
  and remote access, with native Khiops training options and model formats.

## Install

```bash
uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"
```

## Train, predict, evaluate

```python
from khiops_duckdb import deploy_model, evaluate_predictor, train_predictor

report, model = train_predictor(
    "data.parquet",
    target="target",
    output_dir="results/train",
)
predictions = deploy_model(
    "test.parquet", model=model, output_dir="results/predict",
)
evaluation = evaluate_predictor(
    "test.parquet", model=model, output_dir="results/evaluate",
)
```

All 13 table-based core functions accept a file path or DuckDB relation.
Native Khiops options are passed as keyword arguments. Models, reports and
predictions stay in `output_dir`; without it, outputs go to a unique folder
under `khiops-results/`.

## Databases and queries

```python
import duckdb

with duckdb.connect("warehouse.duckdb", read_only=True) as con:
    report, model = train_predictor(
        con.table("customers"), target="target", output_dir="results",
    )
```

Other databases and remote files use your configured DuckDB connection.
You manage access and credentials; the bridge manages temporary data.
Local disk space is required for TSV snapshots.

**[Get started](https://khiopslab.github.io/khiops-duckdb/)** or run the
**[Parquet notebook](sandbox/train_parquet.ipynb)** with self-contained sample data.
The [source guide](https://khiopslab.github.io/khiops-duckdb/sources.html) covers
multiple tables and reader options.

## Reuse data

```python
from khiops_duckdb import materialize, train_predictor

data = materialize("train.parquet", cache_key="training-v1")
report, model = train_predictor(data, target="target", output_dir="results")
```

Reuse the snapshot across jobs and launches. Change `cache_key` when the data
changes. Use `with materialize(...) as data:` for automatic cleanup on exit,
or call `data.close()` to remove a retained snapshot explicitly.

See [dataset lifetimes](https://khiopslab.github.io/khiops-duckdb/datasets.html),
the [BigQuery example](https://khiopslab.github.io/khiops-duckdb/sources.html#bigquery),
and [custom dictionaries](https://khiopslab.github.io/khiops-duckdb/core/index.html#your-dictionary-optional).

## Develop

```bash
uv sync --group dev
uv run python -c "import duckdb; duckdb.connect().install_extension('sqlite')"
uv run pytest
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

On Windows, expose Khiops' installed MPI DLLs before running the engine:
``$env:PATH = "$(Resolve-Path .venv/Library/bin);$env:PATH"`` (PowerShell).
This is needed for serial execution on low-core machines with Khiops 11.

## License

[BSD 3-Clause Clear](LICENSE).
