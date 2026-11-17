"""DuckDB types, exported text and Khiops types."""

from collections.abc import Mapping, Sequence
from typing import Literal

import duckdb

from khiops_duckdb._formats import FORMAT_KEYS, strftime_format

KhiopsType = Literal[
    "Categorical", "Numerical", "Text", "Date", "Time", "Timestamp", "TimestampTZ"
]

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
_TYPES = {
    "Categorical",
    "Numerical",
    "Text",
    "Date",
    "Time",
    "Timestamp",
    "TimestampTZ",
}
_FLOATING = {"float", "double"}
_FREE_TEXT = {"varchar", "enum", "null", "sqlnull"}
_ZONED = "timestamp with time zone"


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def readable_as(type_id: str, kind: str) -> bool:
    """Whether Khiops can read the exported text of a DuckDB type as ``kind``."""
    if kind in {"Categorical", "Text"} or type_id in _FREE_TEXT:
        return True
    if kind == "Numerical":
        return type_id in _NUMERIC
    if kind == "TimestampTZ":
        return type_id == _ZONED
    return _TEMPORAL.get(type_id) == kind


def type_mismatch(column: str, type_id: str, kind: str) -> str:
    return (
        f"Column {column!r} has DuckDB type {type_id!r}: its exported text cannot "
        f"be read by Khiops as {kind}. Cast the column in SQL first."
    )


def check_relation(relation: object) -> duckdb.DuckDBPyRelation:
    if not isinstance(relation, duckdb.DuckDBPyRelation):
        raise TypeError("relation must be a DuckDBPyRelation.")
    columns = relation.columns
    if not columns or any(not name or "\n" in name or "\r" in name for name in columns):
        raise ValueError("Columns must have nonempty, single-line names.")
    if len({name.casefold() for name in columns}) != len(columns):
        raise ValueError("Column names must be unique, ignoring case.")
    return relation


def check_names(
    names: Sequence[str], columns: Sequence[str], role: str
) -> tuple[str, ...]:
    if isinstance(names, str) or any(not isinstance(name, str) for name in names):
        raise TypeError(f"{role} must be a sequence of column names, not a string.")
    if len(set(names)) != len(names) or not set(names).issubset(columns):
        raise ValueError(f"{role} columns must exist and must not be repeated.")
    return tuple(names)


def khiops_types(
    relation: duckdb.DuckDBPyRelation,
    key: Sequence[str],
    overrides: Mapping[str, KhiopsType],
) -> dict[str, KhiopsType]:
    columns = relation.columns
    if not set(overrides).issubset(columns):
        raise ValueError("Type overrides must refer to existing columns.")
    if any(value not in _TYPES for value in overrides.values()):
        raise ValueError(f"Supported Khiops types: {', '.join(sorted(_TYPES))}.")
    if any(overrides.get(name, "Categorical") != "Categorical" for name in key):
        raise ValueError("Key columns must be Categorical.")
    type_ids = [dtype.id for dtype in relation.types]
    for name, type_id in zip(columns, type_ids, strict=True):
        if name in overrides and not readable_as(type_id, overrides[name]):
            raise TypeError(type_mismatch(name, type_id, overrides[name]))
    return {
        name: (
            "Categorical"
            if name in key
            else overrides[name]
            if name in overrides
            else _infer(type_id, name)
        )
        for name, type_id in zip(columns, type_ids, strict=True)
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


def export_projection(
    relation: duckdb.DuckDBPyRelation,
    declared: Mapping[str, tuple[str, str | None]] | None = None,
) -> duckdb.DuckDBPyRelation:
    """Project each column to the text Khiops reads.

    ``declared`` maps a column to its Khiops type and format in the dictionary.
    """
    expressions = []
    for name, dtype in zip(relation.columns, relation.types, strict=True):
        source = quote(name)
        kind, khiops_format = (declared or {}).get(name, (None, None))
        if dtype.id in _TEMPORAL:
            expression = _temporal_text(name, dtype.id, kind, khiops_format)
        else:
            expression = _export_text(source, dtype.id)
        expressions.append(f"coalesce(CAST({expression} AS VARCHAR), '') AS {source}")
    return relation.project(", ".join(expressions))


def _export_text(source: str, type_id: str) -> str:
    if type_id in _FLOATING:
        return f"CASE WHEN isfinite({source}) THEN {source} END"
    if type_id in _NUMERIC:
        return source
    return f"replace(replace(CAST({source} AS VARCHAR), chr(13), ' '), chr(10), ' ')"


def _temporal_text(
    name: str, type_id: str, kind: str | None, khiops_format: str | None
) -> str:
    if kind is None or kind not in FORMAT_KEYS:
        kind, khiops_format = _TEMPORAL[type_id], None
    pattern = strftime_format(kind, khiops_format)
    if pattern is None:
        raise ValueError(
            f"Variable {name!r} declares {khiops_format!r}, which is not a Khiops "
            f"{kind} format."
        )
    code, zone = pattern
    source = quote(name)
    if type_id == "time":
        return f"strftime(DATE '1970-01-01' + {source}, '{code}')"
    if type_id == _ZONED:
        source = f"timezone('UTC', {source})"
    text = f"strftime({source}, '{code}')" + (f" || '{zone}'" if zone else "")
    return f"CASE WHEN isfinite({source}) THEN {text} END"
