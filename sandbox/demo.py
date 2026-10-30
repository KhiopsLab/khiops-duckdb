"""Exemple multi-table autonome utilisant le véritable moteur Khiops."""

import tempfile
from pathlib import Path

import duckdb
import khiops.core as kh

from khiops_duckdb import Table, materialize

with duckdb.connect() as connection, tempfile.TemporaryDirectory() as output:
    customers = connection.sql(
        """SELECT i::VARCHAR id, (i % 2)::VARCHAR target
           FROM range(80) source(i)"""
    )
    orders = connection.sql(
        """SELECT (i // 2)::VARCHAR id, i::VARCHAR order_id, i % 4 amount
           FROM range(160) source(i)"""
    )
    with materialize(
        Table(customers, key=("id",)),
        additional_tables={
            "orders": Table(orders, key=("id", "order_id")),
        },
    ) as data:
        report, model = kh.train_predictor(
            **data.core_args,
            target_variable="target",
            analysis_report_file_path=str(Path(output) / "report.khj"),
            sample_percentage=100,
            use_complement_as_test=False,
            max_trees=0,
            max_cores=1,
        )
        assert Path(report).is_file()
        assert Path(model).is_file()
