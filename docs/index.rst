Khiops DuckDB
=============

.. rst-class:: hero-tagline

   Your data. One call. A trained model.

Go from files or SQL to a Khiops model, without writing export scripts or
collecting a full pandas DataFrame.

.. rst-class:: source-tags

   ``Parquet`` ``CSV`` ``JSON`` ``SQL`` ``Multiple tables``

.. container:: quickstart-panel

   .. rubric:: Start with a file

   .. code-block:: python

      from khiops_duckdb import train_predictor

      report, model = train_predictor(
          "data.parquet", target="target", output_dir="results",
      )

   You choose the target. We handle scalar schema inference, the dictionary and
   temporary files. Your model and report stay in ``results/``.

.. rst-class:: action-links

   :doc:`Train and predict <core/index>`
   :doc:`Run the notebook <demo>`
   :doc:`API reference <api>`

.. container:: install-panel

   .. rubric:: Install

   .. code-block:: bash

      uv pip install "git+https://github.com/KhiopsLab/khiops-duckdb.git"

Less plumbing. More modeling.
------------------------------

.. container:: benefit-grid

   .. container:: benefit-card

      .. rubric:: Skip the export scripts

      Files, SQL results or attached databases: use the same source-first API.
      Keep your DuckDB queries, extensions and credentials.

   .. container:: benefit-card

      .. rubric:: Skip the pandas detour

      Core tasks stream temporary TSV snapshots instead of collecting a full
      DataFrame. Budget local disk space, not an extra pandas-sized copy.

   .. container:: benefit-card

      .. rubric:: Use related tables

      Declare the keys between customers and orders. Let Khiops construct
      relational features instead of flattening everything by hand.

Training is only the beginning. Predict, evaluate, recode or train coclustering
models through the same interface, with native Khiops options and model formats.
:doc:`Choose your data source <sources>` or find a
:ref:`function or class <api-objects>` in the reference.

.. toctree::
   :maxdepth: 1
   :caption: Documentation
   :hidden:

   core/index
   sources
   datasets
   demo
   api
