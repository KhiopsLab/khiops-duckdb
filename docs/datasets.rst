Reuse data
==========

One function, two lifetimes. Pass the resulting ``Dataset`` to any high-level task.

Temporary
---------

.. code-block:: python

   from khiops_duckdb import materialize, train_predictor, train_recoder

   with materialize("train.parquet") as data:
       report, model = train_predictor(data, target="churn", output_dir="runs/model")
       report, recoder = train_recoder(data, target="churn", output_dir="runs/recoder")

Both jobs read the same TSV. Leaving ``with`` removes the snapshot, not the
results, including when a job raises an exception.

Persistent
----------

.. code-block:: python

   from khiops_duckdb import materialize, train_predictor

   data = materialize(
       "train.parquet", cache_key="customers-v1", cache_dir="cache",
   )
   report, model = train_predictor(data, target="churn", output_dir="runs/model")

After restarting Python, reopen it without the original source or connection:

.. code-block:: python

   data = materialize(cache_key="customers-v1", cache_dir="cache")

An existing key reuses its snapshot **without checking the source for changes**.
Choose a new key, such as ``"customers-v2"``, to export updated data.

An ordinary call keeps its files until explicit removal, even when Python exits
or the ``Dataset`` object is deleted. Omit ``cache_key`` for a fresh snapshot;
use a key to reopen it across launches.

Both forms accept files, relations, ``Source``, ``Table``, ``additional_tables``
and ``connection``. See :doc:`sources`.

Files and lifetime
------------------

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - File
     - Behavior
   * - Snapshot TSV files
     - Removed on exit from ``with`` or by explicit ``close``/removal.
   * - ``data.dictionary_file_path``
     - Generated input schema (``schema.kdic``), with the snapshot's lifetime.
       Not a trained model.
   * - Training reports and model ``.kdic``
     - Kept in the job's ``output_dir``, outside the snapshot.
   * - Your input files and custom ``.kdic``
     - Not changed or deleted.

**A cache key does not disable context cleanup.** Exiting
``with materialize(..., cache_key="customers-v1")`` removes that cached version too.
Use ordinary calls for shared or recurring jobs.

A hard stop skips Python's context cleanup. Completed keyed snapshots remain
reusable; incomplete staging files are removed on the next preparation with the
same key. There is no automatic expiry.

Remove explicitly
-----------------

After **all jobs and Khiops subprocesses have stopped**, call ``data.close()``
or remove a version by key:

.. code-block:: python

   from khiops_duckdb import remove_dataset

   remove_dataset(cache_key="customers-v1", cache_dir="cache")

Use different output directories for concurrent jobs. Keep sufficient local
disk space for the uncompressed snapshots. Without a key, ``cache_dir`` or
``directory``, fresh snapshots use the system temporary directory.
