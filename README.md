# Khiops DuckDB

[![CI](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml/badge.svg)](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/ci.yaml)
[![Docs](https://github.com/KhiopsLab/khiops-duckdb/actions/workflows/docs.yaml/badge.svg)](https://khiopslab.github.io/khiops-duckdb/)
[![Release](https://img.shields.io/github/v/release/KhiopsLab/khiops-duckdb?include_prereleases)](https://github.com/KhiopsLab/khiops-duckdb/releases)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-BSD--3--Clause--Clear-blue)](LICENSE)

Use any source queryable by **DuckDB 2.x** with **Khiops**.
No connector wrappers, estimator subclasses, or monkey patches.

## Install

Until the first PyPI release:

```bash
uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"
```

## Use

```python
from pathlib import Path

import duckdb
import khiops.core as kh
from khiops_duckdb import materialize

with duckdb.connect() as con:
    source = con.read_parquet("data/*.parquet")
    with materialize(source) as data:
        kh.train_predictor(
            **data.core_args,
            target_variable="target",
            analysis_report_file_path=str(Path("report.khj").resolve()),
        )
```

Replace `source` with any DuckDB relation: SQL, CSV, JSON, Parquet, Arrow,
an attached database, a remote filesystem, or an extension query.
Extensions, credentials, and source access stay on your DuckDB connection.

`materialize` streams each relation once into temporary Khiops TSV files and
builds its dictionary. Reuse `data.table_args` with an existing model for
deployment. Files are removed on context exit; keep reports and predictions
outside that temporary directory.

### Multiple tables

```python
from khiops_duckdb import Table, materialize

with materialize(
    Table(con.table("customers"), key=("customer_id",)),
    additional_tables={
        "orders": Table(con.table("orders"), key=("customer_id", "order_id")),
    },
) as data:
    # data.core_args works with Khiops' native training and analysis functions.
    ...
```

Nested paths (`orders/items`) and one-to-one tables (`entity=True`) are supported.
Keys are categorical and sorted lexically, not numerically.

### Scikit-learn

```python
from khiops.sklearn import KhiopsClassifier

with materialize(source) as data:
    X = data.to_sklearn()  # Explicitly loads the snapshot into memory.
y = X["main_table"][0].pop("target")
model = KhiopsClassifier().fit(X, y)
predictions = model.predict(X)
```

This uses Khiops' public DataFrame dataset interface, also available to its
regressors, encoders, and coclustering estimators.
Khiops 11 re-infers multi-table prediction keys: conversion rejects affected
keys (for example `"001"`) rather than changing them. Use the core path for those.

## Scope

- Source support is DuckDB's, not a hard-coded connector list. Extensions may
  need installation, credentials, or platform-specific dependencies.
- No pandas conversion on the core path. Local disk space is required for TSV
  snapshots and optional DuckDB sorting spill files.
- Scalar types are inferred. Use `Table(..., types={"body": "Text"})` to override
  them; explicitly cast nested, binary, and interval values in SQL or via a type
  override. Khiops' own numerical and temporal precision limits still apply.
- CR/LF in text become spaces, matching Khiops' single-line record format.
  NULL and empty strings share Khiops' missing-value representation.
  Invalid keys and nonfinite numbers raise errors.

[Documentation](https://khiopslab.github.io/khiops-duckdb/) includes database and
remote-source examples.

## Develop

```bash
uv sync --group dev
uv run python -c "import duckdb; duckdb.connect().install_extension('sqlite')"
uv run pre-commit install
uv run pytest
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
uv build
```

On Windows, expose Khiops' installed MPI DLLs before running the engine:
``$env:PATH = "$(Resolve-Path .venv/Library/bin);$env:PATH"`` (PowerShell).
This is needed for serial execution on low-core machines with Khiops 11.

The SQLite extension is installed before tests; tests themselves use local data.
CI checks Python 3.11–3.14 and Linux/macOS/Windows. It builds pure-Python wheels,
documentation and same-repository PR previews. Publishing to PyPI/TestPyPI is
manual and requires configuring the corresponding trusted publisher.

Structure and tooling follow [Khisto](https://github.com/KhiopsML/khisto-python).
The unrelated histogram implementation, native C++ build and binary signing are
replaced by the DuckDB adapter and standard Python packaging.

## License

[BSD 3-Clause Clear](LICENSE).
