# Changelog

## 0.2.0

Breaking: the package is reduced to two functions over a DuckDB relation.
Khiops tasks are called directly through `khiops.core`.

- `export_data_table(relation, output_data_table_path,
  dictionary_file_path_or_domain, dictionary_name)` writes Khiops' default
  tab-separated format, replaces line breaks in values with spaces, writes only
  the columns the given dictionary stores, sorts by its key, and writes
  multiple files for `s3://` and `gs://` patterns.
- `build_dictionary_from_relation(relation, dictionary_name, key=...,
  variable_types=..., dictionary_domain=..., parent_dictionary_name=...,
  entity=...)` builds a `khiops.core.DictionaryDomain` from the relation's
  schema, including multi-table links. With `output_dictionary_file_path`, it
  saves the dictionary file and keeps an existing one unless `overwrite=True`.
- Both functions reject a column whose exported text Khiops could not read in
  the type the dictionary declares, such as a `TIMESTAMP` declared `Date`.
- Dates and times are written in the format the dictionary declares
  (`DateFormat`, `TimeFormat`, `TimestampFormat`, `TimestampTZFormat`), for
  every format Khiops documents, and otherwise in Khiops' native formats.
  Fractions of a second are truncated to milliseconds.
- `variable_types` accepts `TimestampTZ` for `TIMESTAMPTZ` columns.
- `read_bigquery(query, project=..., connection=...)` streams a BigQuery result
  as a DuckDB relation. It needs the new optional `gcp` extra
  (`google-cloud-bigquery`), not a DuckDB extension.
- The export logs columns it does not write (`INFO`) and dictionary variables
  without a column (`WARNING`) through the `khiops_duckdb` logger.
- Removed the 13 `khiops.core` wrappers, `Source`, `Table`, `Dataset`,
  `materialize`, `remove_dataset`, the snapshot cache and `to_sklearn`.
- Removed the direct `pandas` and `filelock` dependencies; `khiops` still
  installs pandas.
- The export no longer validates data: NaN and infinity are written as missing,
  and key checks are left to `khiops.core.check_database`.

## 0.1.0

- Source-first wrappers for all 13 table-consuming Khiops core functions, with
  direct file/URL inputs, native model deployment, and persistent output paths.
- `Source` declarations for file formats, reader options and multi-table schemas.
- DuckDB 2.x relations to native Khiops dictionaries and temporary TSV files.
- Single, nested multi-table, and one-to-one schemas.
- Explicit in-memory conversion for Khiops' scikit-learn interface.
- Tests, documentation, examples, CI, and package publishing workflows.
