"""Sources DuckDB pour Khiops."""

from khiops_duckdb._schema import KhiopsType
from khiops_duckdb.core import (
    build_dictionary_from_data_table,
    check_database,
    deploy_coclustering,
    deploy_model,
    deploy_predictor_for_metrics,
    detect_data_table_format,
    evaluate_predictor,
    extract_keys_from_data_table,
    sort_data_table,
    train_coclustering,
    train_instance_variable_coclustering,
    train_predictor,
    train_recoder,
)
from khiops_duckdb.dataset import Dataset, Table, materialize
from khiops_duckdb.source import Source, SourceLike

__all__ = [
    "Dataset",
    "KhiopsType",
    "Source",
    "SourceLike",
    "Table",
    "build_dictionary_from_data_table",
    "check_database",
    "deploy_coclustering",
    "deploy_model",
    "deploy_predictor_for_metrics",
    "detect_data_table_format",
    "evaluate_predictor",
    "extract_keys_from_data_table",
    "materialize",
    "sort_data_table",
    "train_coclustering",
    "train_instance_variable_coclustering",
    "train_predictor",
    "train_recoder",
]
