Khiops DuckDB
=============

Train Khiops models directly from Parquet, CSV, JSON, or a DuckDB query.

.. code-block:: bash

   uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"

.. code-block:: python

   from khiops_duckdb import train_predictor

   report, model = train_predictor(
       "data.parquet", target="target", output_dir="results",
   )

.. toctree::
   :maxdepth: 1

   core/index
   sources
   demo
   api
