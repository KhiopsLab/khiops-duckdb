"""Check the installed package without development dependencies."""

from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

import khiops_duckdb
from khiops_duckdb import build_dictionary_from_relation, export_data_table

assert int(version("duckdb").split(".")[0]) == 2
assert Path(khiops_duckdb.__file__).with_name("py.typed").is_file()
with duckdb.connect() as connection, TemporaryDirectory() as directory:
    relation = connection.sql(
        "SELECT * FROM (VALUES ('002', 3.5), ('001', 2.5)) t(id, x)"
    )
    dictionary_domain = build_dictionary_from_relation(relation, "Customer", key=["id"])
    data_table_path = export_data_table(
        relation, Path(directory) / "customers.tsv", dictionary_domain, "Customer"
    )
    assert dictionary_domain.get_dictionary("Customer").key == ["id"]
    assert Path(data_table_path).read_bytes() == b"id\tx\n001\t2.5\n002\t3.5\n"
