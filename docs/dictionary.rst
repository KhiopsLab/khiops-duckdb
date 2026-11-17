The dictionary file
===================

``build_dictionary_from_relation`` writes the ``.kdic`` on the first run and
keeps it afterwards. Edit it freely: the export follows what it says. To rebuild
it from the data, pass ``overwrite=True`` or delete the file.

Edit the dictionary
-------------------

.. list-table::
   :header-rows: 1
   :widths: 42 58

   * - Edit in the ``.kdic``
     - Effect on the next export
   * - Delete a variable's line
     - The column is no longer exported.
   * - Mark a variable ``Unused``
     - The column is still exported.
   * - Change a variable's type
     - Rejected if Khiops could not read the column as that type.
   * - Declare a ``DateFormat``, ``TimeFormat`` or ``TimestampFormat``
     - Dates and times are written in that format.
   * - Change the key
     - The table is sorted by the new key.
   * - Add a variable computed by a rule
     - Nothing is exported for it.

.. _train-test-split:

Train and test split
--------------------

Keep the split column's line in the ``.kdic`` and mark it ``Unused``. It is
still exported, so Khiops can select on it without learning from it:

.. code-block:: python

   report, model = kh.train_predictor(
       dictionary_domain, "Customer", data_table_path, "churn",
       "results/report.khj",
       selection_variable="split", selection_value="train",
       sample_percentage=100,   # the default keeps only 70% of them
   )
   kh.evaluate_predictor(
       model, "SNB_Customer", data_table_path, "results/evaluation.khj",
       selection_variable="split", selection_value="test",
   )

When the data changes
---------------------

The export logs what no longer matches the dictionary:

* ``INFO``: columns not exported because the dictionary does not store them,
  such as a new column in the data.
* ``WARNING``: dictionary variables without a column. Khiops stops if it
  needs one of them.

.. code-block:: python

   import logging

   logging.basicConfig(level=logging.INFO)
