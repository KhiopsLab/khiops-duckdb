"""Ouverture des sources des API de haut niveau."""

from collections.abc import Mapping
from contextlib import AbstractContextManager, ExitStack, nullcontext
from os import PathLike, fspath
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import duckdb

from khiops_duckdb.dataset import Dataset, FileFormat, Table, materialize
from khiops_duckdb.dataset import Source as Source
from khiops_duckdb.dataset import SourceLike as SourceLike


def _materialize_source(
    source: SourceLike | Dataset,
    *,
    additional_tables: Mapping[str, SourceLike] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> AbstractContextManager[Dataset]:
    if isinstance(source, Dataset):
        if additional_tables or connection is not None:
            raise ValueError(
                "A Dataset already contains its tables. Do not supply "
                "additional_tables or connection."
            )
        source._ensure_available()
        return nullcontext(source)
    return materialize(
        source, additional_tables=additional_tables, connection=connection
    )


def _resolve_tables(
    source: SourceLike,
    additional_tables: Mapping[str, SourceLike] | None,
    connection: duckdb.DuckDBPyConnection | None,
    stack: ExitStack,
) -> dict[str, Table]:
    if additional_tables and "" in additional_tables:
        raise ValueError("Additional table data paths cannot be empty.")
    tables = {"": source, **(additional_tables or {})}
    if connection is None and any(_is_file(value) for value in tables.values()):
        connection = stack.enter_context(duckdb.connect())
    return {name: _resolve(value, connection) for name, value in tables.items()}


def _is_file(source: SourceLike) -> bool:
    data = source.data if isinstance(source, Source) else source
    return isinstance(data, (str, PathLike))


def _resolve(
    source: SourceLike,
    connection: duckdb.DuckDBPyConnection | None,
) -> Table:
    if isinstance(source, Table):
        return source
    spec = source if isinstance(source, Source) else Source(source)
    if spec.format is not None and spec.format not in {"csv", "json", "parquet"}:
        raise ValueError("format must be 'csv', 'json' or 'parquet'.")
    if isinstance(spec.data, duckdb.DuckDBPyRelation):
        if spec.format is not None or spec.options:
            raise ValueError(
                "File format and reader options cannot apply to a relation."
            )
        relation = spec.data
    elif isinstance(spec.data, (str, PathLike)):
        if connection is None:
            raise RuntimeError("A DuckDB connection is required to read files.")
        path = fspath(spec.data)
        if not path:
            raise ValueError("Source paths cannot be empty.")
        format = spec.format or _file_format(path)
        options = dict(spec.options)
        if format == "parquet":
            relation = connection.read_parquet(path, **options)
        elif format == "json":
            relation = connection.read_json(path, **options)
        else:
            if _suffix(path) in {".tsv", ".tab"}:
                options.setdefault("delimiter", "\t")
            relation = connection.read_csv(path, **options)
    else:
        raise TypeError(
            "Sources must be paths, URLs, DuckDB relations, Source or Table."
        )
    return Table(relation, key=spec.key, types=spec.types, entity=spec.entity)


def _suffix(path: str) -> str:
    filename = urlsplit(path).path if "://" in path else path
    suffixes = PurePosixPath(filename).suffixes
    if suffixes and suffixes[-1].lower() in {".gz", ".gzip", ".zst", ".zstd", ".bz2"}:
        suffixes.pop()
    return suffixes[-1].lower() if suffixes else ""


def _file_format(path: str) -> FileFormat:
    suffix = _suffix(path)
    if suffix in {".parquet", ".pq"}:
        return "parquet"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return "json"
    if suffix in {".csv", ".tsv", ".tab", ".txt"}:
        return "csv"
    raise ValueError(
        "Cannot infer the source format. Use Source(path, format='csv', 'json' "
        "or 'parquet'), or pass a DuckDB relation. For databases and SQL, pass "
        "connection.table(...) or connection.sql(...)."
    )
