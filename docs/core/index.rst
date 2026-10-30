Train and predict
=================

Train directly from a file, then use the saved model:

.. code-block:: python

   from khiops_duckdb import deploy_model, evaluate_predictor, train_predictor

   report, model = train_predictor(
       "train.parquet", target="target", output_dir="results/train",
   )
   predictions = deploy_model(
       "test.parquet", model=model, output_dir="results/predict",
   )
   evaluation = evaluate_predictor(
       "test.parquet", model=model, output_dir="results/evaluate",
   )

Replace ``"target"`` with the column you want to predict.
The returned values are paths to the saved report, model and output files.
Without ``output_dir``, each call creates a unique folder in ``khiops-results/``.

Native Khiops options work as keyword arguments, for example ``max_cores=1``.
The same file-or-relation interface supports recoding, coclustering, and all
other table-based core tasks; see :doc:`../api`.

For database tables, SQL queries or multiple tables, see :doc:`../sources`.
