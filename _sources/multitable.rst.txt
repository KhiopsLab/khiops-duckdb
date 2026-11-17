Multiple tables
===============

One dictionary call and one export per table, all with the same dictionary
file:

.. code-block:: python

   dictionary_file_path = "schema.kdic"
   build_dictionary_from_relation(
       customers, "Customer", key=["id"],
       output_dictionary_file_path=dictionary_file_path,
   )
   build_dictionary_from_relation(
       orders, "Order", key=["id", "order_id"], parent_dictionary_name="Customer",
       output_dictionary_file_path=dictionary_file_path,
   )
   dictionary_domain = build_dictionary_from_relation(
       address, "Address", key=["id"], parent_dictionary_name="Customer",
       entity=True, output_dictionary_file_path=dictionary_file_path,
   )

   relations = {"Customer": customers, "Order": orders, "Address": address}
   data_table_path = export_data_table(
       customers, "Customer.tsv", dictionary_domain, "Customer",
   )
   additional_data_tables = {}
   for data_path in dictionary_domain.extract_data_paths("Customer"):
       name = dictionary_domain.get_dictionary_at_data_path(data_path).name
       additional_data_tables[data_path] = export_data_table(
           relations[name], f"{name}.tsv", dictionary_domain, name,
       )

   report, model = kh.train_predictor(
       dictionary_domain, "Customer", data_table_path, "churn",
       "results/report.khj", additional_data_tables=additional_data_tables,
   )

Rules
-----

* Build parents first. A child key starts with its parent's key.
* To rebuild the file, pass ``overwrite=True`` on the table without a parent.
* ``parent_dictionary_name`` links the table as a ``Table``: several records
  per parent record. A table can itself be a parent.
* ``entity=True`` links it as an ``Entity``: at most one record per parent
  record, with the parent's key.
* Khiops requires every table that has a key to be sorted by it. The export
  does it when given the dictionary. Without the dictionary the file is
  unsorted, and Khiops stops with ``Unsorted record``.
* Keys are sorted as text: ``10`` comes before ``2``.
* The loop asks Khiops for the data paths, so the script still works if you
  rename a table variable in the ``.kdic``.
* The export does not check that keys are unique or present.
  ``kh.check_database`` does.
