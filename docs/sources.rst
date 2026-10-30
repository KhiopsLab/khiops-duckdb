Data sources
============

Supported sources
-----------------

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Source
     - Pass to the API
   * - Parquet (``.parquet``, ``.pq``)
     - File path, URL or glob.
   * - CSV, TSV, TAB, TXT
     - File path, URL or glob; DuckDB-supported compression.
   * - JSON, JSONL, NDJSON
     - File path, URL or glob.
   * - DuckDB tables and SQL results
     - ``con.table(...)`` or ``con.sql(...)``.
   * - SQLite, PostgreSQL, MySQL
     - Attach with a compatible DuckDB extension, then pass a relation.
   * - BigQuery
     - Use the ``bigquery`` community extension; example below.
   * - HTTP(S), S3, Google Cloud Storage, Azure
     - Remote file URL and a configured DuckDB connection.
   * - pandas, Polars, Arrow
     - Convert to a DuckDB relation first; not accepted directly.
   * - Materialized ``Dataset``
     - Pass it directly to reuse its TSV files.

Database/cloud extensions and credentials belong to your DuckDB connection.
The library does not install connectors or configure cloud identity for you.

Files
-----

Use paths, URLs or file globs for Parquet, CSV, TSV, JSON and JSONL.
Switch formats without changing your training code:

.. code-block:: python

   from khiops_duckdb import train_predictor

   report, model = train_predictor("data/*.parquet", target="target")

Use ``Source`` for reader options or type overrides. For example, preserve
leading zeros in a CSV identifier:

.. code-block:: python

   from khiops_duckdb import Source

   source = Source("data.csv", options={"dtype": {"id": "VARCHAR"}})
   report, model = train_predictor(source, target="target")

For an unknown file extension, specify ``Source(path, format="csv")``.

Databases and SQL
-----------------

Filter or join with SQL, then train on the result. No intermediate file to
manage, and no new connection or credential configuration:

.. code-block:: python

   import duckdb

   with duckdb.connect("warehouse.duckdb", read_only=True) as con:
       source = con.sql("SELECT * FROM customers WHERE active")
       report, model = train_predictor(source, target="target")

Other databases use DuckDB extensions. Configure attachments and credentials on
your connection first. For remote files, pass it with ``connection=con``.
See `DuckDB data import <https://duckdb.org/docs/stable/data/overview.html>`_.

BigQuery
--------

Use `Application Default Credentials
<https://cloud.google.com/docs/authentication/application-default-credentials>`_
and grant BigQuery query/read permissions. A compatible build of the
`BigQuery community extension
<https://duckdb.org/community_extensions/extensions/bigquery>`_ is required.

.. code-block:: python

   import duckdb
   from khiops_duckdb import materialize, train_predictor

   with duckdb.connect() as con:
       con.execute("INSTALL bigquery FROM community")
       con.execute("LOAD bigquery")
       source = con.sql("""
           SELECT customer_id, spend, churn
           FROM bigquery_query('my-project', $$
               SELECT customer_id, spend, churn
               FROM `my-project.analytics.training`
               WHERE event_date >= DATE '2026-10-01'
                 AND event_date < DATE '2026-11-01'
           $$)
       """)
       data = materialize(
           source, cache_key="customers-2026-10", cache_dir="cache",
       )

   report, model = train_predictor(data, target="churn", output_dir="results")

Replace the project, table and columns. GoogleSQL runs in BigQuery: select only
needed columns and filter your partition column to control scanned data.
On later launches, :doc:`reopen the materialized dataset <datasets>` without querying
BigQuery again. Its ``schema.kdic`` is inferred; ``model`` is the trained
dictionary. See :doc:`core/index` to supply your own ``.kdic``.

Multiple tables
---------------

Keep customers and orders as separate tables. Declare their keys with ``Source``
so Khiops can construct relational features, rather than flattening them yourself:

.. code-block:: python

   report, model = train_predictor(
       Source("customers.parquet", key=("id",)),
       additional_tables={
           "orders": Source("orders.parquet", key=("id", "order_id")),
       },
       target="target",
       output_dir="results",
   )

Child keys start with their parent's key. Main-table keys must be unique.
Use ``entity=True`` for one-to-one tables and paths such as ``"orders/items"``
for nested tables. Not every native task supports multiple tables.
