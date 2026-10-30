API reference
=============

Functions you call. Objects you configure. Files you keep.
Import high-level functions from ``khiops_duckdb`` or ``khiops_duckdb.core``.

.. rst-class:: api-nav

   :ref:`Sources <api-sources>`
   :ref:`Training <api-training>`
   :ref:`Deployment <api-deployment>`
   :ref:`Table utilities <api-tables>`
   :ref:`Advanced <api-advanced>`

.. _api-objects:

Shared arguments
----------------

All high-level functions accept:

* ``source``: a path, URL, file glob, DuckDB relation,
  :class:`~khiops_duckdb.Source` or :class:`~khiops_duckdb.Table`.
* ``connection=None``: an existing DuckDB connection for file readers,
  extensions and credentials. It stays open after the call.
* ``output_dir=None``: where default output files are saved. Without it, each
  file-producing call creates a unique directory under ``khiops-results/``.
  Explicit native output paths take precedence.
* ``**options``: native Khiops task options. The signatures below expand the
  task-specific keywords you will usually need.

Training, model deployment and evaluation also accept
``additional_tables={path: source, ...}`` where the native task supports it.
See :doc:`sources` for keys and multi-table schemas.

``target`` aliases ``target_variable``; ``model`` aliases
``dictionary_file_path_or_domain``. Supply only one spelling.
An ambiguous model dictionary needs an explicit ``dictionary_name``.
Input-format arguments are managed by the bridge; file-reader settings belong
in :class:`~khiops_duckdb.Source`.

Outputs survive the call; temporary input files do not. Native errors propagate.

.. _api-sources:

Configure a source
------------------

Most calls only need a filename. Use ``Source`` when you need keys, type overrides
or reader options:

.. code-block:: python

   from khiops_duckdb import Source

   customers = Source("customers.parquet", key=("id",))
   comments = Source("comments.csv", types={"body": "Text"})
   export = Source("data.export", format="csv", options={"delimiter": "|"})

.. autoclass:: khiops_duckdb.Source

``types`` accepts ``Categorical``, ``Numerical``, ``Text``, ``Date``, ``Time`` and
``Timestamp``. ``format`` is ``"csv"``, ``"json"`` or ``"parquet"``.
The default mappings are independent empty dictionaries for each instance.

.. currentmodule:: khiops_duckdb.core

.. _api-training:

Train models
------------

.. py:function:: train_predictor(source, *, target, output_dir=None, **options) -> tuple[str, str | None]

   Train a supervised predictor, or prepare data without a target.

   :param target: Target column name. Use ``""`` for unsupervised preparation.
   :returns: ``(report_path, model_path)``. The model path is ``None`` when the
             target is empty.

   .. code-block:: python

      report, model = train_predictor(
          "train.parquet", target="churn", output_dir="results/train",
          max_cores=1,
      )

.. py:function:: train_recoder(source, *, target="", output_dir=None, **options) -> tuple[str, str]

   Train a recoding model for transforming data into engineered features.
   Omitting ``target`` runs an unsupervised recoding workflow.

   :returns: ``(report_path, recoder_dictionary_path)``. Use
             :func:`deploy_model` to apply the recoder.

.. py:function:: train_coclustering(source, *, coclustering_variables, output_dir=None, **options) -> str

   Discover groups across two to ten selected variables.

   :param coclustering_variables: List of column names to cocluster.
   :returns: Coclustering report path (``.khcj``).

.. py:function:: train_instance_variable_coclustering(source, *, output_dir=None, **options) -> str

   Train an instance-variable coclustering model.

   :returns: Coclustering report path (``.khcj``).

.. _api-deployment:

Predict and evaluate
--------------------

``model`` accepts a dictionary path, ``Path`` or native ``DictionaryDomain``.
The unique root dictionary, or the only dictionary, is selected automatically.

.. py:function:: deploy_model(source, *, model, output_dir=None, **options) -> str

   Apply a saved predictor, recoder or other native deployment dictionary.

   :param model: Model dictionary returned by training.
   :returns: Deployed table path (TSV by default).

   .. code-block:: python

      predictions = deploy_model(
          "test.parquet", model=model, output_dir="results/predict",
      )

.. py:function:: evaluate_predictor(source, *, model, output_dir=None, **options) -> str

   Evaluate a trained predictor on labeled data.

   :param model: Predictor dictionary.
   :returns: Evaluation report path (``.khj``).

   The source must contain the target column. ``dictionary_name`` also accepts
   the native spelling ``train_dictionary_name`` for this function.

.. py:function:: deploy_predictor_for_metrics(source, *, model, output_dir=None, **options) -> str

   Export predictor output columns for metric computation.

   :returns: Metrics table path.

.. py:function:: deploy_coclustering(source, *, coclustering_file_path, key_variable_names, deployed_variable_name, output_dir=None, **options) -> tuple[str, str]

   Apply a trained coclustering and create its deployment dictionary.

   :param coclustering_file_path: Coclustering report produced by training.
   :param key_variable_names: Names of the categorical key columns.
   :param deployed_variable_name: Coclustering variable to deploy.
   :returns: ``(deployed_table_path, deployment_dictionary_path)``.

   Input must be sorted lexically by the key variables. Use a sorted DuckDB
   relation for repeated observations; do not declare a unique main-table key.
   This task does not accept additional tables.

.. _api-tables:

Inspect and prepare tables
--------------------------

.. py:function:: build_dictionary_from_data_table(source, *, output_dictionary_name="main_table", output_dir=None, **options) -> str

   Ask Khiops to infer a dictionary from the exported table.

   :returns: Dictionary file path (``.kdic``).

   This native task re-infers the snapshot; source keys and type overrides are
   not a substitute for configuring the resulting dictionary.

.. py:function:: check_database(source, *, model=None, **options) -> None

   Validate data against a dictionary. Without ``model``, use the dictionary
   inferred from the source.

   :returns: ``None``. Native validation errors propagate.

.. py:function:: sort_data_table(source, *, sort_variables=None, output_dir=None, **options) -> str

   Sort by ``sort_variables`` or by the supplied dictionary's keys.

   :returns: Sorted table path.

.. py:function:: extract_keys_from_data_table(source, *, output_dir=None, **options) -> str

   Extract key columns from a keyed ``Source``/``Table`` or native dictionary.

   :returns: Keys table path.

.. py:function:: detect_data_table_format(source, **options) -> tuple[bool | None, str | None]

   Detect the format of the normalized TSV snapshot, not the original source.

   :returns: ``(header_line, field_separator)``; values may be ``None`` when
             detection cannot determine them.

Native APIs without data-table inputs, including dictionary/report readers,
``simplify_coclustering`` and ``interpret_predictor``, remain available unchanged
through ``khiops_duckdb.core``.

.. currentmodule:: khiops_duckdb

.. _api-advanced:

Advanced: explicit snapshots
-----------------------------

Use these objects when you need to reuse a snapshot or edit its dictionary.
Most workflows should use the high-level functions above.

.. autoclass:: khiops_duckdb.Table

.. autofunction:: khiops_duckdb.materialize

.. py:class:: Dataset

   Returned by ``materialize``; not intended for direct construction.
   ``dictionary_domain`` exposes the generated dictionary.
   ``data_table_path`` and ``additional_data_tables`` expose temporary file paths,
   valid only inside the materialization context.

   .. autoattribute:: khiops_duckdb.Dataset.core_args

   .. autoattribute:: khiops_duckdb.Dataset.table_args

   .. automethod:: khiops_duckdb.Dataset.to_sklearn

Further reading
---------------

.. toctree::
   :maxdepth: 1

   semantics
   sklearn/index
