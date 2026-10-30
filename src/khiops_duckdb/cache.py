"""Instantanés persistants, versionnés explicitement par l'appelant."""

import hashlib
import json
import shutil
from collections.abc import Mapping
from contextlib import ExitStack
from os import PathLike, replace
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
import khiops.core as kh
from filelock import FileLock

from khiops_duckdb._schema import KhiopsType
from khiops_duckdb.dataset import (
    Dataset,
    SourceLike,
    _Export,
    _materialize_in_directory,
)

_FORMAT_VERSION = 1
_TYPES: dict[str, KhiopsType] = {
    "Categorical": "Categorical",
    "Numerical": "Numerical",
    "Text": "Text",
    "Date": "Date",
    "Time": "Time",
    "Timestamp": "Timestamp",
}


def _materialize_cached(
    main_table: SourceLike | None = None,
    *,
    cache_key: str,
    cache_dir: str | PathLike[str] = ".khiops-cache",
    additional_tables: Mapping[str, SourceLike] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> Dataset:
    root, entry = _location(cache_dir, cache_key)
    if main_table is None and (additional_tables or connection is not None):
        raise ValueError("Reopening a dataset does not accept sources or a connection.")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with FileLock(str(root / f".{entry.name}.lock")):
        _clean_staging(root, entry.name)
        if entry.exists() or entry.is_symlink():
            return _load_dataset(entry, cache_key)
        if main_table is None:
            raise FileNotFoundError(
                f"No materialized dataset for cache_key={cache_key!r}."
            )
        with TemporaryDirectory(
            prefix=f".{entry.name}.staging-", dir=root
        ) as temporary:
            staging = Path(temporary)
            data = _materialize_in_directory(
                main_table, additional_tables, connection, staging
            )
            _write_manifest(data, cache_key)
            replace(staging, entry)
        return _load_dataset(entry, cache_key)


def remove_dataset(
    *,
    cache_key: str,
    cache_dir: str | PathLike[str] = ".khiops-cache",
) -> None:
    """Supprime explicitement un instantané, une fois tous ses jobs arrêtés.

    Le verrou protège les préparations concurrentes, pas les lecteurs. L'appelant
    doit vérifier que tous les jobs et sous-processus Khiops ont terminé.

    Args:
        cache_key: Version à supprimer.
        cache_dir: Répertoire contenant l'instantané.

    Raises:
        FileNotFoundError: Instantané absent.
        ValueError: Le chemin de l'instantané est un lien ou n'est pas un dossier.
    """
    _remove_dataset(cache_key=cache_key, cache_dir=cache_dir, missing_ok=False)


def _remove_dataset(
    *,
    cache_key: str,
    cache_dir: str | PathLike[str],
    missing_ok: bool,
) -> None:
    root, entry = _location(cache_dir, cache_key)
    if not root.is_dir():
        if missing_ok and not root.exists():
            return
        raise FileNotFoundError(f"No cache directory: {root}")
    with FileLock(str(root / f".{entry.name}.lock")):
        _remove_directory(entry, missing_ok=missing_ok)


def _remove_directory(directory: Path, *, missing_ok: bool) -> None:
    if not directory.exists() and not directory.is_symlink():
        if missing_ok:
            return
        raise FileNotFoundError(f"No materialized dataset: {directory}")
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"Dataset must be a directory, not a link: {directory}")
    shutil.rmtree(directory)


def _location(cache_dir: str | PathLike[str], cache_key: str) -> tuple[Path, Path]:
    if not isinstance(cache_key, str):
        raise TypeError("cache_key must be a string.")
    if not cache_key.strip():
        raise ValueError("cache_key cannot be empty.")
    root = Path(cache_dir).expanduser().resolve()
    digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()
    return root, root / digest


def _clean_staging(root: Path, digest: str) -> None:
    for path in root.glob(f".{digest}.staging-*"):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"Unexpected prepared dataset staging path: {path}")
        shutil.rmtree(path)


def _write_manifest(data: Dataset, cache_key: str) -> None:
    tables = [
        {
            "path": path,
            "filename": Path(exported.path).name,
            "key": list(exported.key),
            "types": exported.types,
            "entity": exported.entity,
            "size": Path(exported.path).stat().st_size,
        }
        for path, exported in data._exports.items()
    ]
    with (data.directory / "manifest.json").open("w", encoding="utf-8") as stream:
        json.dump(
            {
                "format_version": _FORMAT_VERSION,
                "cache_key": cache_key,
                "dictionary_name": data.dictionary_name,
                "tables": tables,
            },
            stream,
            indent=2,
        )


def _load_dataset(directory: Path, cache_key: str) -> Dataset:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(
            f"Materialized dataset must be a directory, not a link: {directory}"
        )
    with (directory / "manifest.json").open(encoding="utf-8") as stream:
        metadata: object = json.load(stream)
    if (
        not isinstance(metadata, dict)
        or metadata.get("format_version") != _FORMAT_VERSION
        or metadata.get("cache_key") != cache_key
        or not isinstance(metadata.get("tables"), list)
        or not isinstance(metadata.get("dictionary_name"), str)
    ):
        raise ValueError(f"Incompatible prepared dataset metadata: {directory}")
    exports = dict(
        _read_table(directory, index, record)
        for index, record in enumerate(metadata["tables"])
    )
    if "" not in exports or len(exports) != len(metadata["tables"]):
        raise ValueError(
            "Materialized dataset needs exactly one main table and unique paths."
        )
    for path in exports:
        if path and path.rpartition("/")[0] not in exports:
            raise ValueError(f"Materialized dataset is missing the parent of {path!r}.")
    domain = kh.read_dictionary_file(str(directory / "schema.kdic"))
    domain.get_dictionary(metadata["dictionary_name"])
    cleanup = ExitStack()
    cleanup.callback(
        _remove_dataset,
        cache_key=cache_key,
        cache_dir=directory.parent,
        missing_ok=True,
    )
    return Dataset(
        dictionary_domain=domain,
        dictionary_name=metadata["dictionary_name"],
        data_table_path=exports[""].path,
        additional_data_tables={
            path: exported.path for path, exported in exports.items() if path
        },
        _exports=exports,
        _cleanup=cleanup,
    )


def _read_table(directory: Path, index: int, record: object) -> tuple[str, _Export]:
    if not isinstance(record, dict):
        raise ValueError("Invalid prepared dataset table metadata.")
    path, key, entity = record.get("path"), record.get("key"), record.get("entity")
    if (
        not isinstance(path, str)
        or (path and any(part in {"", ".", ".."} for part in path.split("/")))
        or record.get("filename") != f"table-{index}.tsv"
        or not isinstance(key, list)
        or not all(isinstance(name, str) for name in key)
        or not isinstance(entity, bool)
    ):
        raise ValueError("Invalid prepared dataset table path, keys or entity flag.")
    types = _read_types(record.get("types"))
    if any(name not in types for name in key):
        raise ValueError("Materialized dataset keys must name existing columns.")
    file_path = directory / f"table-{index}.tsv"
    size = record.get("size")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or file_path.is_symlink()
        or not file_path.is_file()
        or file_path.stat().st_size != size
    ):
        raise ValueError(
            f"Materialized dataset input is missing or changed: {file_path}"
        )
    return path, _Export(str(file_path), tuple(key), types, entity)


def _read_types(value: object) -> dict[str, KhiopsType]:
    if not isinstance(value, dict) or not value:
        raise ValueError("Invalid prepared dataset column types.")
    types = {}
    for name, kind in value.items():
        if not isinstance(name, str) or not isinstance(kind, str) or kind not in _TYPES:
            raise ValueError("Invalid prepared dataset column type.")
        types[name] = _TYPES[kind]
    return types
