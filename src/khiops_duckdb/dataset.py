"""Matérialisation des sources au format natif de Khiops."""

from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from os import PathLike
from pathlib import Path
from tempfile import mkdtemp
from types import TracebackType
from typing import Any, Literal, NotRequired, TypeAlias, TypedDict

import duckdb
import khiops.core as kh
import pandas as pd

from khiops_duckdb._schema import KhiopsType, column_types, prepare, quote

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


@dataclass(frozen=True)
class Table:
    """Décrit une table et ses clés de jointure.

    Args:
        relation: Relation appartenant à une connexion DuckDB ouverte.
        key: Colonnes de clé, dans l'ordre de la hiérarchie Khiops.
        types: Types Khiops à imposer à certaines colonnes.
        entity: Relation un-à-un avec le parent, au lieu d'un-à-plusieurs.
    """

    relation: duckdb.DuckDBPyRelation
    key: Sequence[str] = ()
    types: Mapping[str, KhiopsType] = field(default_factory=dict)
    entity: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.relation, duckdb.DuckDBPyRelation):
            raise TypeError("relation must be a DuckDBPyRelation.")
        if not isinstance(self.entity, bool):
            raise TypeError("entity must be a boolean.")
        column_types(self.relation, self.key, self.types)


SourceLike: TypeAlias = _Data | Source | Table


class TableArguments(TypedDict):
    """Arguments communs des tables pour les fonctions de khiops.core."""

    data_table_path: str
    additional_data_tables: dict[str, str]
    header_line: bool
    field_separator: str


class CoreArguments(TableArguments):
    """Arguments des tables et du dictionnaire pour khiops.core."""

    dictionary_file_path_or_domain: kh.DictionaryDomain
    dictionary_name: str


class SklearnDataset(TypedDict):
    """Spécification multi-table publique acceptée par khiops.sklearn."""

    main_table: tuple[pd.DataFrame, list[str] | None]
    additional_data_tables: NotRequired[dict[str, tuple[pd.DataFrame, list[str], bool]]]


@dataclass(frozen=True)
class _Export:
    path: str
    key: tuple[str, ...]
    types: dict[str, KhiopsType]
    entity: bool = False


@dataclass(frozen=True)
class Dataset:
    """Expose un instantané réutilisable et son dictionnaire d'entrée.

    Les fichiers restent sur disque sans bloc ``with``, même après destruction
    de l'objet. ``close`` ou la sortie du bloc ``with`` les supprime.
    Le dictionnaire et les DataFrames déjà chargés restent utilisables.
    """

    dictionary_domain: kh.DictionaryDomain
    data_table_path: str
    additional_data_tables: dict[str, str]
    _exports: Mapping[str, _Export] = field(repr=False)
    dictionary_name: str = "main_table"
    _cleanup: ExitStack | None = field(default=None, repr=False, compare=False)

    @property
    def directory(self) -> Path:
        """Retourne le répertoire de l'instantané, sans les sorties des jobs."""
        return Path(self.data_table_path).parent

    @property
    def dictionary_file_path(self) -> str:
        """Retourne le chemin du schéma d'entrée, et non d'un modèle entraîné."""
        return str(self.directory / "schema.kdic")

    def close(self) -> None:
        """Supprime l'instantané possédé, après l'arrêt de tous ses lecteurs."""
        if self._cleanup is not None:
            self._cleanup.close()

    def __enter__(self) -> "Dataset":
        self._ensure_available()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _ensure_available(self) -> None:
        for path in [self.data_table_path, *self.additional_data_tables.values()]:
            if not Path(path).is_file():
                raise FileNotFoundError(f"Dataset input is missing or closed: {path}")

    @property
    def table_args(self) -> TableArguments:
        """Retourne les arguments des tables, utilisables avec un modèle existant."""
        self._ensure_available()
        return {
            "data_table_path": self.data_table_path,
            "additional_data_tables": self.additional_data_tables.copy(),
            "header_line": True,
            "field_separator": "\t",
        }

    @property
    def core_args(self) -> CoreArguments:
        """Retourne les arguments natifs de khiops.core, sans wrapper de tâche."""
        return {
            **self.table_args,
            "dictionary_file_path_or_domain": self.dictionary_domain,
            "dictionary_name": self.dictionary_name,
        }

    def to_sklearn(self) -> SklearnDataset:
        """Charge les fichiers en mémoire pour l'interface scikit-learn.

        Returns:
            Spécification Khiops contenant des DataFrames pandas indépendants.
            Les dates et heures restent des chaînes.

        Raises:
            ValueError: Khiops réinterpréterait les clés multi-table à la prédiction.
        """
        self._ensure_available()
        frames = {
            path: pd.read_csv(
                exported.path,
                sep="\t",
                dtype={
                    name: "float64" if kind == "Numerical" else "str"
                    for name, kind in exported.types.items()
                },
                keep_default_na=False,
                skip_blank_lines=False,
                na_values={
                    name: [""]
                    for name, kind in exported.types.items()
                    if kind == "Numerical"
                },
            )
            for path, exported in self._exports.items()
        }
        if self.additional_data_tables:
            keys = list(self._exports[""].key)
            inferred_keys = pd.read_csv(self.data_table_path, sep="\t", usecols=keys)
            if not inferred_keys.equals(frames[""][keys]):
                raise ValueError(
                    "Khiops 11 re-infers multi-table prediction keys, which would "
                    "change these identifiers. Use the core API, or explicitly "
                    "project nonnumeric keys without pandas missing-value tokens."
                )
        spec: SklearnDataset = {
            "main_table": (
                frames[""],
                list(self._exports[""].key) or None,
            ),
        }
        if self.additional_data_tables:
            spec["additional_data_tables"] = {
                path: (frames[path], list(exported.key), exported.entity)
                for path, exported in self._exports.items()
                if path
            }
        return spec


def materialize(
    main_table: SourceLike | None = None,
    *,
    additional_tables: Mapping[str, SourceLike] | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
    directory: str | PathLike[str] | None = None,
    cache_key: str | None = None,
    cache_dir: str | PathLike[str] | None = None,
) -> Dataset:
    """Crée ou rouvre un instantané à réutiliser dans plusieurs jobs.

    Args:
        main_table: Fichier, URL, relation DuckDB, Source ou Table. Facultatif
            pour rouvrir une version existante avec ``cache_key``.
        additional_tables: Sources secondaires par chemin Khiops.
        connection: Connexion des lecteurs de fichiers ; reste ouverte.
        directory: Répertoire parent existant, sans ``cache_key`` ni ``cache_dir``.
        cache_key: Version immuable, à changer après une mise à jour des données.
        cache_dir: Répertoire à créer si nécessaire. Avec une clé, sa valeur par
            défaut est ``.khiops-cache`` ; sans clé ni répertoire, utilise le
            répertoire temporaire système.

    Returns:
        Dataset conservé sur disque sans nettoyage automatique. Un bloc ``with``
        supprime les fichiers à sa sortie, même avec une clé de cache. Sinon,
        appeler ``close`` ou ``remove_dataset`` explicitement. Une clé existante
        réutilise ses fichiers sans relire ni comparer les sources.

    Raises:
        TypeError: Relation ou type DuckDB non pris en charge.
        ValueError: Schéma, hiérarchie, clé ou valeur numérique non valide.
        FileNotFoundError: Version absente et source non fournie.
        duckdb.Error: Lecture de source, conversion ou écriture impossible.
    """
    from khiops_duckdb.cache import _materialize_cached, _remove_directory

    if directory is not None and (cache_key is not None or cache_dir is not None):
        raise ValueError(
            "Use directory alone, or cache_dir with an optional cache_key."
        )
    if cache_key is not None:
        return _materialize_cached(
            main_table,
            cache_key=cache_key,
            cache_dir=cache_dir if cache_dir is not None else ".khiops-cache",
            additional_tables=additional_tables,
            connection=connection,
        )
    if main_table is None:
        raise ValueError("main_table is required unless cache_key is provided.")
    if cache_dir is not None:
        directory = Path(cache_dir).expanduser().resolve()
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    with ExitStack() as resources:
        path = Path(mkdtemp(prefix="khiops-duckdb-", dir=directory)).resolve()
        resources.callback(_remove_directory, path, missing_ok=True)
        data = _materialize_in_directory(
            main_table, additional_tables, connection, path
        )
        return replace(data, _cleanup=resources.pop_all())


def _materialize_in_directory(
    main_table: SourceLike,
    additional_tables: Mapping[str, SourceLike] | None,
    connection: duckdb.DuckDBPyConnection | None,
    directory: Path,
) -> Dataset:
    from khiops_duckdb.source import _resolve_tables

    with ExitStack() as connections:
        tables = _resolve_tables(main_table, additional_tables, connection, connections)
        _check_hierarchy(tables)
        exports = {}
        with duckdb.connect() as validator:
            for index, (path, table) in enumerate(tables.items()):
                file_path = str(directory / f"table-{index}.tsv")
                exported = _export(table, file_path)
                _check_values(validator, exported, unique=not path or table.entity)
                exports[path] = exported
    domain = _dictionary_domain(exports)
    domain.export_khiops_dictionary_file(str(directory / "schema.kdic"))
    return Dataset(
        dictionary_domain=domain,
        data_table_path=exports[""].path,
        additional_data_tables={
            path: exported.path for path, exported in exports.items() if path
        },
        _exports=exports,
    )


def _check_hierarchy(tables: Mapping[str, Table]) -> None:
    names = {"main_table"}
    if tables[""].entity:
        raise ValueError("The main table cannot be an entity.")
    for path, table in tables.items():
        if not path:
            continue
        fragments = path.split("/")
        if any(fragment in {"", ".", ".."} for fragment in fragments):
            raise ValueError(f"Invalid table data path: {path!r}.")
        parent_path = "/".join(fragments[:-1])
        if parent_path not in tables:
            raise ValueError(f"Missing parent table for {path!r}.")
        parent = tables[parent_path]
        if not parent.key or not table.key:
            raise ValueError("Every table in a multi-table dataset needs a key.")
        if tuple(table.key[: len(parent.key)]) != tuple(parent.key):
            raise ValueError(f"The key of {path!r} must start with its parent's key.")
        if table.entity and tuple(table.key) != tuple(parent.key):
            raise ValueError(f"Entity {path!r} must have exactly its parent's key.")
        name = fragments[-1]
        if name in names:
            raise ValueError(f"Table names must be globally unique: {name!r}.")
        names.add(name)
        if name in parent.relation.columns:
            raise ValueError(f"Table {path!r} conflicts with a parent column.")


def _export(table: Table, file_path: str) -> _Export:
    types = column_types(table.relation, table.key, table.types)
    prepare(table.relation, table.key, types).write_csv(
        file_path,
        sep="\t",
        header=True,
        quotechar='"',
        escapechar='"',
        na_rep="",
    )
    return _Export(file_path, tuple(table.key), types, table.entity)


def _check_values(
    connection: duckdb.DuckDBPyConnection, exported: _Export, *, unique: bool
) -> None:
    checks = []
    for name in exported.key:
        column = quote(name)
        invalid = (
            f"{column} IS NULL OR contains({column}, chr(10)) "
            f"OR contains({column}, chr(13))"
        )
        checks.append(
            (
                f"bool_or({invalid})",
                f"Key {name!r} contains a missing or multiline value.",
            )
        )
    if unique and exported.key:
        keys = ", ".join(quote(name) for name in exported.key)
        checks.append(
            (
                f"count(*) != count(DISTINCT ({keys}))",
                "Main table and entity keys must be unique.",
            )
        )
    for name, kind in exported.types.items():
        if kind == "Numerical":
            invalid = f"NOT isfinite(CAST({quote(name)} AS DOUBLE))"
            checks.append(
                (
                    f"bool_or({invalid})",
                    f"Numerical column {name!r} contains NaN or infinity.",
                )
            )
    if checks:
        staged = connection.read_csv(
            exported.path, sep="\t", header=True, all_varchar=True
        )
        flags = staged.aggregate(", ".join(sql for sql, _ in checks)).fetchall()[0]
        for flag, (_, message) in zip(flags, checks, strict=True):
            if flag:
                raise ValueError(message)


def _dictionary_domain(exports: Mapping[str, _Export]) -> kh.DictionaryDomain:
    domain = kh.DictionaryDomain()
    for path in sorted(exports, key=lambda value: (value.count("/"), value)):
        exported = exports[path]
        dictionary = kh.Dictionary()
        dictionary.name = path.split("/")[-1] if path else "main_table"
        dictionary.key = list(exported.key)
        dictionary.root = not path and len(exports) > 1
        for name, kind in exported.types.items():
            variable = kh.Variable()
            variable.name, variable.type = name, kind
            if kind == "Time":
                variable.meta_data.add_value("TimeFormat", "HH:MM:SS.")
            elif kind == "Timestamp":
                variable.meta_data.add_value("TimestampFormat", "YYYY-MM-DD HH:MM:SS.")
            dictionary.add_variable(variable)
        domain.add_dictionary(dictionary)
        if path:
            parent_path = path.rpartition("/")[0]
            parent_name = parent_path.split("/")[-1] if parent_path else "main_table"
            variable = kh.Variable()
            variable.name = dictionary.name
            variable.type = "Entity" if exported.entity else "Table"
            variable.object_type = dictionary.name
            domain.get_dictionary(parent_name).add_variable(variable)
    return domain
