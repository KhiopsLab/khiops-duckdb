API reference
=============

All 13 table-based core functions accept ``source`` first, then native options
as keyword arguments. ``target`` aliases ``target_variable`` and ``model``
aliases ``dictionary_file_path_or_domain``. An ambiguous model dictionary needs
an explicit ``dictionary_name``.

Training and evaluation keep their native return values. File-producing commands
that normally return ``None`` instead return the output path.
``check_database`` still returns ``None``. ``detect_data_table_format`` describes
the normalized TSV snapshot, not the original file.

Model/report-only functions remain unchanged through ``khiops_duckdb.core``.

High-level core functions
--------------------------

.. autoclass:: khiops_duckdb.Source
   :members:

.. automodule:: khiops_duckdb.core
   :members:

Low-level snapshots
-------------------

.. autoclass:: khiops_duckdb.Table
   :members:

.. autofunction:: khiops_duckdb.materialize

.. autoclass:: khiops_duckdb.Dataset
   :members:

Further details
---------------

.. toctree::
   :maxdepth: 1

   semantics
   sklearn/index
