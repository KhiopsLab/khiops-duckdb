"""DuckDB data tables and dictionaries for Khiops."""

from khiops_duckdb._schema import KhiopsType
from khiops_duckdb.dictionary import build_dictionary_from_relation
from khiops_duckdb.export import export_data_table
from khiops_duckdb.gcp import read_bigquery

__all__ = [
    "KhiopsType",
    "build_dictionary_from_relation",
    "export_data_table",
    "read_bigquery",
]
