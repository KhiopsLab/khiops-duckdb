"""Khiops dictionaries built from DuckDB relations."""

from collections.abc import Mapping, Sequence
from os import PathLike
from pathlib import Path

import duckdb
import khiops.core as kh

from khiops_duckdb._schema import (
    KhiopsType,
    check_names,
    check_relation,
    khiops_types,
)


def build_dictionary_from_relation(
    relation: duckdb.DuckDBPyRelation,
    dictionary_name: str,
    *,
    key: Sequence[str] = (),
    variable_types: Mapping[str, KhiopsType] | None = None,
    dictionary_domain: kh.DictionaryDomain | None = None,
    parent_dictionary_name: str | None = None,
    entity: bool = False,
    output_dictionary_file_path: str | PathLike[str] | None = None,
    overwrite: bool = False,
) -> kh.DictionaryDomain:
    """Build the Khiops dictionary of a relation from its schema.

    Call once per table, parents first, with the same ``dictionary_domain`` or
    the same ``output_dictionary_file_path``.

    Args:
        relation: DuckDB relation to describe.
        dictionary_name: Name of the dictionary.
        key: Key columns, in order. Export a keyed table with its dictionary,
            which sorts it.
        variable_types: Khiops types to declare instead of the inferred ones.
            Values are not converted.
        dictionary_domain: Domain to add the dictionary to. A new one by default.
        parent_dictionary_name: Dictionary this table belongs to.
        entity: Link as ``Entity`` (one record per parent) instead of ``Table``.
        output_dictionary_file_path: Dictionary file to save the domain to. A
            dictionary already in the file is kept as it is.
        overwrite: On the table without a parent, rebuild the file from scratch.

    Returns:
        The domain holding the dictionary.

    Raises:
        TypeError: Invalid argument, or a type Khiops could not read.
        ValueError: Invalid name, key, type, parent link or file option.
    """
    relation = check_relation(relation)
    columns = check_names(key, relation.columns, "key")
    kinds = khiops_types(relation, columns, variable_types or {})
    if not isinstance(dictionary_name, str) or not dictionary_name:
        raise ValueError("dictionary_name must be a nonempty string.")
    if not isinstance(entity, bool):
        raise TypeError("entity must be a boolean.")
    domain, path = _domain(
        dictionary_domain,
        output_dictionary_file_path,
        overwrite,
        restart=overwrite and parent_dictionary_name is None,
    )
    if domain.get_dictionary(dictionary_name) is not None:
        if path is not None and not overwrite:
            return domain
        raise ValueError(
            f"The domain already has a dictionary named {dictionary_name!r}."
            + (" Set overwrite=True on the table without a parent." if path else "")
        )
    owner = _parent(domain, dictionary_name, columns, parent_dictionary_name, entity)
    dictionary = kh.Dictionary()
    dictionary.name, dictionary.key = dictionary_name, list(columns)
    for column, kind in kinds.items():
        dictionary.add_variable(_variable(column, kind))
    domain.add_dictionary(dictionary)
    if owner is not None:
        link = kh.Variable()
        link.name, link.object_type = dictionary_name, dictionary_name
        link.type = "Entity" if entity else "Table"
        owner.add_variable(link)
        owner.root = not _is_child(domain, owner.name)
    if path is not None:
        domain.export_khiops_dictionary_file(str(path))
    return domain


def _domain(
    dictionary_domain: kh.DictionaryDomain | None,
    output_dictionary_file_path: str | PathLike[str] | None,
    overwrite: bool,
    *,
    restart: bool,
) -> tuple[kh.DictionaryDomain, Path | None]:
    if output_dictionary_file_path is None:
        if overwrite:
            raise ValueError("overwrite requires output_dictionary_file_path.")
        if dictionary_domain is None:
            return kh.DictionaryDomain(), None
        return dictionary_domain, None
    if dictionary_domain is not None:
        raise ValueError(
            "Pass dictionary_domain or output_dictionary_file_path, not both."
        )
    path = Path(output_dictionary_file_path)
    if path.is_file() and not restart:
        return kh.read_dictionary_file(str(path)), path
    return kh.DictionaryDomain(), path


def _variable(column: str, kind: KhiopsType) -> kh.Variable:
    variable = kh.Variable()
    variable.name, variable.type = column, kind
    if kind == "Time":
        variable.meta_data.add_value("TimeFormat", "HH:MM:SS.")
    elif kind == "Timestamp":
        variable.meta_data.add_value("TimestampFormat", "YYYY-MM-DD HH:MM:SS.")
    return variable


def _parent(
    domain: kh.DictionaryDomain,
    name: str,
    key: tuple[str, ...],
    parent: str | None,
    entity: bool,
) -> kh.Dictionary | None:
    if parent is None:
        if entity:
            raise ValueError("entity=True requires parent_dictionary_name=...")
        return None
    owner = domain.get_dictionary(parent)
    if owner is None:
        raise ValueError(
            f"Unknown parent dictionary {parent!r}. Build it first and pass "
            "the same dictionary_domain."
        )
    parent_key = tuple(owner.key)
    if not parent_key or key[: len(parent_key)] != parent_key:
        raise ValueError(
            f"The key of {name!r} must start with the key of {parent!r}: "
            f"{list(parent_key)}."
        )
    if entity and key != parent_key:
        raise ValueError(f"Entity {name!r} must have exactly the key of {parent!r}.")
    if any(variable.name == name for variable in owner.variables):
        raise ValueError(f"{name!r} conflicts with a variable of {parent!r}.")
    return owner


def _is_child(domain: kh.DictionaryDomain, name: str) -> bool:
    return any(
        variable.object_type == name
        for dictionary in domain.dictionaries
        for variable in dictionary.variables
    )
