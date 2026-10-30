"""Conversion explicite des types et expressions DuckDB."""

from collections.abc import Mapping, Sequence
from typing import Literal

import duckdb

KhiopsType = Literal["Categorical", "Numerical", "Text", "Date", "Time", "Timestamp"]

_NUMERIC = {
    "tinyint",
    "smallint",
    "integer",
    "bigint",
    "hugeint",
    "utinyint",
    "usmallint",
    "uinteger",
    "ubigint",
    "uhugeint",
    "float",
    "double",
    "decimal",
}
_TEMPORAL: dict[str, KhiopsType] = {
    "date": "Date",
    "time": "Time",
    "timestamp": "Timestamp",
    "timestamp_s": "Timestamp",
    "timestamp_ms": "Timestamp",
    "timestamp_ns": "Timestamp",
    "timestamp with time zone": "Timestamp",
}
_TYPES = {"Categorical", "Numerical", "Text", "Date", "Time", "Timestamp"}


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def column_types(
    relation: duckdb.DuckDBPyRelation,
    key: Sequence[str],
    overrides: Mapping[str, KhiopsType],
) -> dict[str, KhiopsType]:
    columns = relation.columns
    if not columns or any(not name or "\n" in name or "\r" in name for name in columns):
        raise ValueError("Columns must have nonempty, single-line names.")
    if len({name.casefold() for name in columns}) != len(columns):
        raise ValueError("Column names must be unique, ignoring case.")
    if isinstance(key, str) or any(not isinstance(name, str) for name in key):
        raise TypeError("key must be a sequence of column names, not a string.")
    if len(set(key)) != len(key) or not set(key).issubset(columns):
        raise ValueError("Key columns must exist and must not be repeated.")
    if not set(overrides).issubset(columns):
        raise ValueError("Type overrides must refer to existing columns.")
    if any(value not in _TYPES for value in overrides.values()):
        raise ValueError(f"Supported Khiops types: {', '.join(sorted(_TYPES))}.")
    if any(overrides.get(name, "Categorical") != "Categorical" for name in key):
        raise ValueError("Key columns must be Categorical.")
    return {
        name: (
            "Categorical"
            if name in key
            else overrides[name]
            if name in overrides
            else _infer(dtype.id, name)
        )
        for name, dtype in zip(columns, relation.types, strict=True)
    }


def _infer(type_id: str, column: str) -> KhiopsType:
    if type_id in _NUMERIC:
        return "Numerical"
    if type_id in _TEMPORAL:
        return _TEMPORAL[type_id]
    if type_id in {"varchar", "enum", "uuid", "boolean", "null", "sqlnull"}:
        return "Categorical"
    raise TypeError(
        f"Unsupported DuckDB type {type_id!r} for {column!r}. "
        "Project it with CAST(... AS VARCHAR), or supply a Khiops type override."
    )


def prepare(
    relation: duckdb.DuckDBPyRelation,
    key: Sequence[str],
    types: Mapping[str, KhiopsType],
) -> duckdb.DuckDBPyRelation:
    expressions = []
    for name, dtype in zip(relation.columns, relation.types, strict=True):
        source = quote(name)
        kind = types[name]
        if kind in {"Categorical", "Text"}:
            expression = f"CAST({source} AS VARCHAR)"
            if name not in key:
                expression = (
                    f"replace(replace({expression}, chr(13), ' '), chr(10), ' ')"
                )
        elif kind == "Numerical":
            expression = source if dtype.id in _NUMERIC else f"CAST({source} AS DOUBLE)"
        elif kind == "Timestamp" and dtype.id == "timestamp with time zone":
            expression = f"timezone('UTC', {source})"
        else:
            expression = f"CAST({source} AS {kind.upper()})"
        if kind == "Timestamp":
            expression = f"strftime({expression}, '%Y-%m-%d %H:%M:%S.%f')"
        expression = f"coalesce(CAST({expression} AS VARCHAR), '')"
        expressions.append(f"{expression} AS {source}")
    prepared = relation.project(", ".join(expressions))
    if key:
        prepared = prepared.order(
            ", ".join(f'{quote(name)} COLLATE "binary" ASC' for name in key)
        )
    return prepared
