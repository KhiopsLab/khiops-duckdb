# Changelog

## Unreleased

- Unified, source-first `materialize` returning a reusable `Dataset`: ordinary
  calls retain files; `with` removes them on exit.
- Named `cache_key` versions, atomic cross-process preparation, interrupted-export
  recovery and explicit removal with `close` or `remove_dataset`.
- Supported datasource list, BigQuery example and explicit input/model
  dictionary lifetimes in the user guides.

## 0.1.0

- Source-first wrappers for all 13 table-consuming Khiops core functions, with
  direct file/URL inputs, native model deployment, and persistent output paths.
- `Source` declarations for file formats, reader options and multi-table schemas.
- DuckDB 2.x relations to native Khiops dictionaries and temporary TSV files.
- Single, nested multi-table, and one-to-one schemas.
- Explicit in-memory conversion for Khiops' scikit-learn interface.
- Tests, documentation, examples, CI, and package publishing workflows.
