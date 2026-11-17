Data sources
============

Both functions take a DuckDB relation. Extensions and credentials belong to your
DuckDB connection.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Source
     - How to get a relation
   * - Parquet, CSV, JSON
     - ``con.read_parquet(...)``, ``con.read_csv(...)``, ``con.read_json(...)``
   * - DuckDB tables and SQL results
     - ``con.table(...)`` or ``con.sql(...)``
   * - SQLite, PostgreSQL, MySQL
     - Attach with the DuckDB extension, then ``con.sql(...)``
   * - pandas, Polars, Arrow
     - ``con.from_df(frame)`` or ``con.from_arrow(table)``
   * - BigQuery
     - ``read_bigquery(...)``, below

Good to know
------------

* CSV types are inferred by DuckDB. Keep identifiers as text with
  ``con.read_csv("data.csv", dtype={"id": "VARCHAR"})``.
* Each export runs the query again. For an expensive query, materialize it
  first with ``CREATE TEMP TABLE ... AS`` and pass ``con.table(...)``.

.. _bigquery:

BigQuery
--------

``read_bigquery`` installs with pip and needs no DuckDB extension, so it works
where the network blocks extension downloads.

.. code-block:: bash

   uv pip install "khiops-duckdb[gcp] @ git+https://github.com/KhiopsLab/khiops-duckdb.git"

.. code-block:: python

   from khiops_duckdb import read_bigquery

   customers = read_bigquery("""
       SELECT customer_id, spend, churn
       FROM `my-project.analytics.training`
       WHERE event_date >= DATE '2026-10-01'
   """, connection=con)
   data_table_path = export_data_table(
       customers, "customers.tsv", dictionary_domain, "Customer",
   )

* It uses `Application Default Credentials
  <https://cloud.google.com/docs/authentication/application-default-credentials>`_
  and their project, or ``project="..."``.
* The query runs in BigQuery: select only the columns you need and filter the
  partition column.
* ``connection=con`` puts the result in your connection, where SQL can use it
  by its variable name: ``con.sql("FROM customers JOIN orders USING (id)")``.
  Without it, DuckDB's default connection is used.
* The result is streamed and can be read once. To read it several times, store
  it first: ``customers.create("customers")``, then ``con.table("customers")``.
