Data sources
============

Files
-----

Pass a Parquet, CSV, TSV, JSON or JSONL path. URLs and file globs work too:

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

Pass a relation from your DuckDB connection:

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

Declare the join keys with ``Source``:

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
