Khiops DuckDB
=============

.. rst-class:: hero-tagline

   Run Khiops on any data DuckDB can read.

.. rst-class:: source-tags

   ``Parquet`` ``CSV`` ``JSON`` ``PostgreSQL`` ``MySQL`` ``SQLite``
   ``BigQuery`` ``S3`` ``GCS`` ``pandas`` ``Polars`` ``Arrow``

Files, databases, cloud buckets, DataFrames: if DuckDB can query it, Khiops can
learn from it. Filter and join in SQL, then train. No export script to write,
no pandas copy of your data.

.. code-block:: bash

   uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"

From a source to a model
------------------------

.. code-block:: python

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
       dictionary_domain, "Customer", data_table_path, "churn",
       "results/report.khj",
   )
   kh.deploy_model(model, "SNB_Customer", data_table_path, "results/scores.tsv")

Change one line to change the source: a SQL query, a database table, a bucket.
See :doc:`sources`.

Two functions, then plain Khiops
--------------------------------

* ``build_dictionary_from_relation`` drafts the Khiops dictionary from the
  schema and saves it. On later runs it keeps the file, so you can
  :doc:`adjust it by hand <dictionary>`.
* ``export_data_table`` writes the data table that dictionary describes: only
  its columns, in its date formats, sorted by its key as Khiops requires.

Training, deployment and evaluation are ``khiops.core``, unchanged.
Related tables work the same way: see :doc:`multitable`.
For BigQuery, ``khiops-duckdb[gcp]`` adds :ref:`read_bigquery <bigquery>`.

.. toctree::
   :maxdepth: 1
   :hidden:

   sources
   dictionary
   multitable
   semantics
   api
