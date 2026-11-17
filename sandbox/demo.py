"""Multi-table example: build the dictionary once, edit it by hand, rerun."""

import logging
from pathlib import Path

import duckdb
import khiops.core as kh

from khiops_duckdb import build_dictionary_from_relation, export_data_table

logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
work = Path(__file__).parent / "demo_results"
work.mkdir(exist_ok=True)
dictionary_file_path = work / "schema.kdic"

with duckdb.connect() as connection:
    relations = {
        "Customer": connection.sql(
            """SELECT i AS id, (i % 2)::VARCHAR AS target,
                      DATE '2026-01-01' + i::INTEGER AS since
               FROM range(80) source(i)"""
        ),
        "Order": connection.sql(
            """SELECT i // 2 AS id, i AS order_id, i % 4 AS amount
               FROM range(160) source(i)"""
        ),
    }

    build_dictionary_from_relation(
        relations["Customer"],
        "Customer",
        key=["id"],
        output_dictionary_file_path=dictionary_file_path,
    )
    dictionary_domain = build_dictionary_from_relation(
        relations["Order"],
        "Order",
        key=["id", "order_id"],
        parent_dictionary_name="Customer",
        output_dictionary_file_path=dictionary_file_path,
    )
    data_table_path = export_data_table(
        relations["Customer"], work / "Customer.tsv", dictionary_domain, "Customer"
    )
    additional_data_tables = {}
    for data_path in dictionary_domain.extract_data_paths("Customer"):
        name = dictionary_domain.get_dictionary_at_data_path(data_path).name
        additional_data_tables[data_path] = export_data_table(
            relations[name], work / f"{name}.tsv", dictionary_domain, name
        )

report, model = kh.train_predictor(
    dictionary_domain,
    "Customer",
    data_table_path,
    "target",
    str(work / "report.khj"),
    additional_data_tables=additional_data_tables,
    sample_percentage=100,
    use_complement_as_test=False,
    max_trees=0,
    max_cores=1,
)
assert Path(report).is_file()
assert Path(model).is_file()
