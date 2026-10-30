Data sources
============

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
