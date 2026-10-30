Data sources
============

Anything DuckDB can expose as a relation can cross the same boundary. Source
support depends on DuckDB and its extensions; this package adds no source-specific
APIs and does not guarantee every external service is available on every platform.

Files and Python objects
------------------------

.. code-block:: python

   source = con.read_csv("data/*.csv")
   source = con.read_json("data/*.json")
   source = con.read_parquet("data/**/*.parquet", hive_partitioning=True)
   source = con.from_df(frame)
   source = con.from_arrow(arrow_table)
   source = con.sql("SELECT * FROM observations WHERE amount > 0")

Use ``con.register_filesystem(filesystem)`` for supported fsspec filesystems.
Install that filesystem's dependencies separately.

Databases
---------

Configure DuckDB once, then pass a relation as usual:

.. code-block:: python

   con.install_extension("sqlite")
   con.load_extension("sqlite")
   con.execute("ATTACH 'warehouse.sqlite' AS warehouse (TYPE sqlite, READ_ONLY)")
   source = con.table("warehouse.observations")

PostgreSQL and MySQL follow the same pattern with their DuckDB extensions:

.. code-block:: python

   con.install_extension("postgres")
   con.load_extension("postgres")
   # PGSERVICE names a configured libpq service; keep credentials out of code.
   con.execute(
       "ATTACH '' AS warehouse (TYPE postgres, READ_ONLY)"
   )
   source = con.sql("SELECT * FROM warehouse.public.observations")

Set ``PGSERVICE`` and configure its service file before connecting. For MySQL,
use DuckDB's ``mysql`` extension and its documented connection configuration.
Live PostgreSQL/MySQL servers are not part of this repository's automated tests;
SQLite and attached DuckDB databases are.

Remote files and object stores
------------------------------

.. code-block:: python

   con.install_extension("httpfs")
   con.load_extension("httpfs")
   con.execute("CREATE SECRET (TYPE s3, PROVIDER credential_chain)")
   source = con.read_parquet("s3://bucket/prefix/*.parquet")
   # Or con.read_parquet("https://host.example/data.parquet").

Secrets and extension setup belong to your connection. The bridge never copies
them into its output. Only load trusted extensions and execute trusted SQL.
Errors propagate; a failed export removes its temporary files.

See the official `DuckDB data import documentation
<https://duckdb.org/docs/stable/data/overview.html>`_ and
`extension documentation <https://duckdb.org/docs/stable/extensions/overview.html>`_.
