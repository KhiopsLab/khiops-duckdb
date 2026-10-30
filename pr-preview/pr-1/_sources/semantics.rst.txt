Data semantics
==============

* Each source relation is executed once, sequentially. Validation and pandas
  conversion reread the local snapshot, not the original source. Cross-table
  transactional consistency is the caller's responsibility.
* Core processing streams to TSV without collecting a pandas DataFrame. The
  caller controls DuckDB's memory limit and sorting spill directory. Budget local
  disk for the uncompressed snapshots; they live in a private temporary directory.
* ``directory=...`` selects an existing parent directory. Only the newly created
  child is removed, on success or failure. Place reports and deployed predictions
  elsewhere. This option belongs to the low-level ``materialize`` API.
  High-level core calls automatically separate snapshots from persistent outputs;
  ``output_dir`` controls outputs, not the snapshot location.
* Strings, booleans, enums, UUIDs and NULL columns default to ``Categorical``;
  numeric scalars to ``Numerical``; dates/times/timestamps to their Khiops types.
  Timezone-aware timestamps are normalized to UTC without changing the connection.
* ``types={"body": "Text"}`` overrides a column's Khiops type. Unsupported types
  (lists, structs, maps, binary, intervals) require an explicit SQL projection or
  type override. Conversion errors are not suppressed.
* CR and LF in non-key text become spaces. Quotes, tabs and Unicode are escaped.
  NULL and empty strings share the native missing-value representation; a fully
  missing row is retained. NaN and infinity are rejected.
* Keys become categorical text and are sorted with binary lexical collation.
  Missing, empty or multiline keys are rejected, as are duplicate main/entity keys.
  Order unkeyed SQL explicitly when row order matters.
* Khiops imposes its own numeric precision, categorical size, date range and
  temporal precision limits (including millisecond timestamp precision).
  In particular, arbitrary-precision DuckDB decimals/integers are not
  losslessly represented by Khiops' numerical model.
* Khiops' normal checks and warnings still govern orphan child records,
  model/schema compatibility and learning constraints.
* Coclustering deployment expects input sorted lexically by its key variables.
  Supply a sorted DuckDB relation when needed. For repeated observations, pass
  ``key_variable_names`` to the task rather than declaring a unique main-table
  key on ``Source``.
* Use ``target=""`` for unsupervised preparation; predictor training then returns
  ``None`` for the model path. Recoding defaults to an empty target.
* Input-format arguments are managed by the bridge. Use
  ``Source(..., options=...)`` for reader options, not ``header_line`` or
  ``field_separator`` on a high-level task. Errors propagate.
* CSV inference happens before Khiops inference: use reader ``dtype`` overrides
  to preserve leading-zero identifiers or boolean-looking labels.

``materialize`` never opens, closes or reconfigures source connections. High-level
file calls open and close a private source connection if none was supplied.
Caller-owned connections are never closed or reconfigured. The separate local
validation connection never handles source credentials.
