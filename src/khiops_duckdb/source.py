"""Ouverture des sources des API de haut niveau."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from os import PathLike, fspath
from pathlib import PurePosixPath
from typing import Any, Literal, TypeAlias
from urllib.parse import urlsplit

import duckdb

from khiops_duckdb._schema import KhiopsType
from khiops_duckdb.dataset import Dataset, Table, materialize

FileFormat: TypeAlias = Literal["csv", "json", "parquet"]
_Data: TypeAlias = str | PathLike[str] | duckdb.DuckDBPyRelation


@dataclass(frozen=True)
class Source:
    """Décrit une source fichier ou une relation et son schéma Khiops.

    Args:
        data: Chemin, URL, motif de fichiers ou relation DuckDB.
        key: Colonnes de clé, dans l'ordre de la hiérarchie.
        types: Types Khiops à imposer à certaines colonnes.
        entity: Relation un-à-un avec le parent.
        format: Format explicite pour les fichiers sans extension reconnue.
        options: Options transmises au lecteur DuckDB, sans modification.
    """

    data: _Data
    key: Sequence[str] = ()
    types: Mapping[str, KhiopsType] = field(default_factory=dict)
    entity: bool = False
    format: FileFormat | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


SourceLike: TypeAlias = _Data | Source | Table


@contextmanager
def _materialize_source(
    source: SourceLike,
    *,
    additional_tables: Mapping[str, SourceLike] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> Iterator[Dataset]:
    with ExitStack() as stack:
        tables = {"": source, **(additional_tables or {})}
        if additional_tables and "" in additional_tables:
            raise ValueError("Additional table data paths cannot be empty.")
        if connection is None and any(_is_file(value) for value in tables.values()):
            connection = stack.enter_context(duckdb.connect())
        resolved = {name: _resolve(value, connection) for name, value in tables.items()}
        yield stack.enter_context(
            materialize(
                resolved.pop(""),
                additional_tables=resolved,
            )
        )


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
