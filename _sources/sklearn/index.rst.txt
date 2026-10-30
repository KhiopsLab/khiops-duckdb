Scikit-learn
============

Khiops 11's scikit-learn interface accepts DataFrames, not file-backed dataset
specifications. ``to_sklearn`` explicitly loads the exported snapshot into memory
and returns its public dataset specification, without patching Khiops internals.

.. code-block:: python

   from khiops.sklearn import KhiopsClassifier
   from khiops_duckdb import materialize

   with materialize(source) as data:
       X = data.to_sklearn()
   y = X["main_table"][0].pop("target")
   classifier = KhiopsClassifier().fit(X, y)
   predictions = classifier.predict(X)

The same specification supports regressors, encoders, and multi-table workflows.
For coclustering, retain the relevant columns and omit the supervised target.
Single-table specifications deliberately omit ``additional_data_tables``.

Each call returns independent DataFrames, usable after the context exits.
Numerical columns become floats; categorical values and keys remain strings,
including leading zeros and literal ``NA`` values. Dates and times remain
strings and are inferred as categorical by Khiops' DataFrame interface. Core-only
type overrides such as ``Text`` do not configure scikit-learn estimators.

Khiops 11 currently re-infers multi-table prediction keys when reading its output.
Numeric-looking strings (including leading zeros), booleans and pandas NA tokens
can therefore change type or value before its merge step. ``to_sklearn`` detects
and rejects affected main keys; use the core path to preserve such identifiers,
or explicitly choose nonnumeric identifiers in your SQL projection. No keys are
silently rewritten.

Predictions follow the exported main-table order, which is lexical key order
for keyed datasets, not necessarily the original source order.
