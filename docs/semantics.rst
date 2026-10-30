Data semantics
==============

* Each source relation is executed once, sequentially. Validation and pandas
  conversion reread the local snapshot, not the original source. Cross-table
  transactional consistency is the caller's responsibility.
* Core processing streams to TSV without collecting a pandas DataFrame. The
  caller controls DuckDB's memory limit and sorting spill directory. Budget local
  disk for the uncompressed snapshots. ``materialize`` creates a private directory;
  with ``cache_key``, it publishes a named version in ``cache_dir``.
* ``directory=...`` selects an existing parent for a fresh snapshot. ``cache_dir``
  creates a parent if necessary; with a key, it defaults to ``.khiops-cache``.
  These options cannot be combined. Place reports and deployed predictions
  outside the snapshot.
  High-level core calls automatically separate snapshots from persistent outputs;
  ``output_dir`` controls outputs, not the snapshot location.
* ``materialize`` returns a ``Dataset`` immediately. Ordinary calls retain files
  even after garbage collection or process exit. ``with`` removes the snapshot
  on exit; ``close()`` removes it explicitly. Both remove keyed versions too.
  Failed exports are cleaned up. High-level tasks borrow caller-provided datasets
  without closing or re-exporting them.
* A cache key identifies an immutable data version, not a live query.
  Cache hits do not compare current source data, schemas or reader options.
  Change the key to refresh. Publication is atomic and serialized per key;
  abandoned staging directories are removed on the next preparation.
* Snapshots never expire automatically. Context exit, ``close()`` and
  ``remove_dataset`` require all readers, including surviving Khiops subprocesses,
  to have stopped. The per-key lock protects writers, not running readers.
* Each snapshot contains ``schema.kdic``, an input schema rather than a trained
  model. Native dictionary options override it per task without changing the
  cached schema file. Training model dictionaries and reports remain in the
  job's output directory.
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

File inputs open and close a private source connection if none was supplied.
Caller-owned connections are never closed or reconfigured. Once materialization
finishes, the snapshot no longer needs its source connection. The separate local
validation connection never handles source credentials.
