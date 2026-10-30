"""Matérialisation de relations DuckDB au format natif de Khiops."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NotRequired, TypedDict

import duckdb
import khiops.core as kh
import pandas as pd

from khiops_duckdb._schema import KhiopsType, column_types, prepare, quote


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
    table: Table
    types: dict[str, KhiopsType]


@dataclass(frozen=True)
class Dataset:
    """Expose les fichiers et le dictionnaire d'un contexte matérialisé.

    Les fichiers sont supprimés à la sortie du contexte ``materialize``.
    Le dictionnaire et les DataFrames déjà chargés restent utilisables.
    """

    dictionary_domain: kh.DictionaryDomain
    data_table_path: str
    additional_data_tables: dict[str, str]
    _exports: Mapping[str, _Export] = field(repr=False)
    dictionary_name: str = "main_table"

    @property
    def table_args(self) -> TableArguments:
        """Retourne les arguments des tables, utilisables avec un modèle existant."""
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
            keys = list(self._exports[""].table.key)
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
                list(self._exports[""].table.key) or None,
            ),
        }
        if self.additional_data_tables:
            spec["additional_data_tables"] = {
                path: (frames[path], list(exported.table.key), exported.table.entity)
                for path, exported in self._exports.items()
                if path
            }
        return spec


@contextmanager
def materialize(
    main_table: Table | duckdb.DuckDBPyRelation,
    *,
    additional_tables: Mapping[str, Table] | None = None,
    directory: str | PathLike[str] | None = None,
) -> Iterator[Dataset]:
    """Exporte les relations une seule fois vers des fichiers TSV temporaires.

    Args:
        main_table: Relation principale ou description complète de la table.
        additional_tables: Tables par chemin Khiops, par exemple ``orders/items``.
        directory: Répertoire parent existant pour le sous-répertoire temporaire.

    Yields:
        Dataset utilisable avec les API natives de Khiops.

    Raises:
        TypeError: Relation ou type DuckDB non pris en charge.
        ValueError: Schéma, hiérarchie, clé ou valeur numérique non valide.
        duckdb.Error: Lecture de source, conversion ou écriture impossible.
    """
    root = main_table if isinstance(main_table, Table) else Table(main_table)
    if additional_tables and "" in additional_tables:
        raise ValueError("Additional table data paths cannot be empty.")
    tables = {"": root, **(additional_tables or {})}
    _check_hierarchy(tables)
    with TemporaryDirectory(prefix="khiops-duckdb-", dir=directory) as temporary:
        exports = {}
        with duckdb.connect() as validator:
            for index, (path, table) in enumerate(tables.items()):
                file_path = str(Path(temporary) / f"table-{index}.tsv")
                exported = _export(table, file_path)
                _check_values(validator, exported, unique=not path or table.entity)
                exports[path] = exported
        yield Dataset(
            dictionary_domain=_dictionary_domain(exports),
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
        if not isinstance(table, Table):
            raise TypeError("Additional tables must be Table instances.")
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
    return _Export(file_path, table, types)


def _check_values(
    connection: duckdb.DuckDBPyConnection, exported: _Export, *, unique: bool
) -> None:
    checks = []
    for name in exported.table.key:
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
    if unique and exported.table.key:
        keys = ", ".join(quote(name) for name in exported.table.key)
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
        dictionary.key = list(exported.table.key)
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
            variable.type = "Entity" if exported.table.entity else "Table"
            variable.object_type = dictionary.name
            domain.get_dictionary(parent_name).add_variable(variable)
    return domain
