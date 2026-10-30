Native Khiops workflows
=======================

Use the generated dictionary and table arguments directly; there is no separate
training API to learn. Keep the DuckDB connection open during materialization.

.. code-block:: python

   from pathlib import Path
   import duckdb
   import khiops.core as kh
   from khiops_duckdb import materialize

   with duckdb.connect() as con:
       source = con.read_csv("observations.csv")
       with materialize(source) as data:
           _, model_path = kh.train_predictor(
               **data.core_args,
               target_variable="target",
               analysis_report_file_path=str(Path("report.khj").resolve()),
           )
           kh.deploy_model(
               model_path,
               "SNB_main_table",
               **data.table_args,
               output_data_table_path=str(Path("predictions.tsv").resolve()),
           )

For unsupervised preparation, use ``target_variable=""``. The same dictionary,
main file and additional-table mapping can be passed to Khiops' other table-based
core functions, including coclustering. Functions without common table parameters
can use ``data.dictionary_domain`` and ``data.data_table_path`` individually.

Multi-table schemas
-------------------

.. code-block:: python

   from khiops_duckdb import Table, materialize

   with materialize(
       Table(con.table("customers"), key=("id",)),
       additional_tables={
           "orders": Table(con.table("orders"), key=("id", "order_id")),
           "orders/items": Table(con.table("items"), key=("id", "order_id")),
           "profile": Table(con.table("profile"), key=("id",), entity=True),
       },
   ) as data:
       # Add derived variables to data.dictionary_domain, or use data.core_args.
       ...

Each child key starts with its parent's key, using the same column names.
Main-table and entity keys are unique. A one-to-many table may repeat its key.
Leaf table names must be globally unique and cannot shadow a parent column.
Declare all parents; mapping insertion order does not matter.
