"""Export of DuckDB relations as Khiops data tables."""

import logging
from os import PathLike, fspath

import duckdb
import khiops.core as kh

from khiops_duckdb._formats import FORMAT_KEYS
from khiops_duckdb._schema import (
    check_relation,
    export_projection,
    quote,
    readable_as,
    type_mismatch,
)

_LOGGER = logging.getLogger("khiops_duckdb")
_VIEW = "__khiops_duckdb_export"
_PATTERN_SCHEMES = ("s3://", "gs://")


def export_data_table(
    relation: duckdb.DuckDBPyRelation,
    output_data_table_path: str | PathLike[str],
    dictionary_file_path_or_domain: str
    | PathLike[str]
    | kh.DictionaryDomain
    | None = None,
    dictionary_name: str | None = None,
) -> str:
    """Write a relation as a Khiops data table.

    The file is tab-separated with a header line. With a dictionary, only the
    columns it stores are written, dates and times follow its formats, and the
    table is sorted by its key.

    Args:
        relation: DuckDB relation to export.
        output_data_table_path: Local path or cloud URI. On ``s3://`` and
            ``gs://``, a ``*`` in the file name writes several unsorted files.
        dictionary_file_path_or_domain: Dictionary file or domain describing
            the table.
        dictionary_name: Dictionary to use. Required with a dictionary.

    Returns:
        ``output_data_table_path`` as a string.

    Raises:
        TypeError: Invalid argument, or a column Khiops could not read.
        ValueError: Invalid path, pattern, dictionary or date format.
        duckdb.Error: The relation could not be read or the file written.
    """
    relation = check_relation(relation)
    dictionary = _dictionary(dictionary_file_path_or_domain, dictionary_name)
    key: tuple[str, ...] = ()
    declared: dict[str, tuple[str, str | None]] = {}
    if dictionary is not None:
        relation, declared = _described_columns(relation, dictionary)
        key = tuple(dictionary.key)
    path = fspath(output_data_table_path)
    if not path:
        raise ValueError("output_data_table_path cannot be empty.")
    prepared = export_projection(relation, declared)
    if "*" in path:
        _write_parts(prepared, path, sorted_export=bool(key))
        return path
    if key:
        prepared = prepared.order(
            ", ".join(f'{quote(name)} COLLATE "binary" ASC' for name in key)
        )
    prepared.write_csv(
        path, sep="\t", header=True, quotechar='"', escapechar='"', na_rep=""
    )
    return path


def _dictionary(
    dictionary_file_path_or_domain: str | PathLike[str] | kh.DictionaryDomain | None,
    dictionary_name: str | None,
) -> kh.Dictionary | None:
    if dictionary_file_path_or_domain is None:
        if dictionary_name is not None:
            raise ValueError("dictionary_name requires dictionary_file_path_or_domain.")
        return None
    if not isinstance(dictionary_name, str) or not dictionary_name:
        raise ValueError(
            "dictionary_name is required with dictionary_file_path_or_domain."
        )
    domain = dictionary_file_path_or_domain
    if isinstance(domain, (str, PathLike)):
        domain = kh.read_dictionary_file(fspath(domain))
    if not isinstance(domain, kh.DictionaryDomain):
        raise TypeError(
            "dictionary_file_path_or_domain must be a dictionary file path "
            "or a DictionaryDomain."
        )
    dictionary = domain.get_dictionary(dictionary_name)
    if dictionary is None:
        raise ValueError(f"No dictionary named {dictionary_name!r}.")
    return dictionary


def _stored_variables(dictionary: kh.Dictionary) -> dict[str, tuple[str, str | None]]:
    stored = {}
    for variable in dictionary.variables:
        if variable.rule or variable.is_relational():
            continue
        if variable.variable_block is not None:
            continue
        format_key = FORMAT_KEYS.get(variable.type)
        declared = variable.meta_data.get_value(format_key) if format_key else None
        stored[variable.name] = (variable.type, declared)
    return stored


def _described_columns(
    relation: duckdb.DuckDBPyRelation, dictionary: kh.Dictionary
) -> tuple[duckdb.DuckDBPyRelation, dict[str, tuple[str, str | None]]]:
    missing = [name for name in dictionary.key if name not in relation.columns]
    if missing:
        raise ValueError(
            f"Key variables {missing} of {dictionary.name!r} are not columns "
            "of the relation."
        )
    stored = _stored_variables(dictionary)
    blocks = {block.name for block in dictionary.variable_blocks if not block.rule}
    columns = []
    for name, dtype in zip(relation.columns, relation.types, strict=True):
        if name in stored and not readable_as(dtype.id, stored[name][0]):
            raise TypeError(type_mismatch(name, dtype.id, stored[name][0]))
        if name in stored or name in blocks:
            columns.append(name)
    if not columns:
        raise ValueError(
            f"No column of the relation is described by dictionary {dictionary.name!r}."
        )
    _report_drift(relation.columns, columns, list(stored), dictionary.name)
    return relation.project(", ".join(quote(name) for name in columns)), stored


def _report_drift(
    available: list[str], exported: list[str], stored: list[str], dictionary_name: str
) -> None:
    ignored = [name for name in available if name not in exported]
    if ignored:
        _LOGGER.info(
            "Columns %s are not stored by dictionary %r and are not exported.",
            ignored,
            dictionary_name,
        )
    absent = [name for name in stored if name not in available]
    if absent:
        _LOGGER.warning(
            "Variables %s of dictionary %r have no column in the relation. "
            "Khiops stops if it requires one of them.",
            absent,
            dictionary_name,
        )


def _write_parts(
    relation: duckdb.DuckDBPyRelation, pattern: str, *, sorted_export: bool
) -> None:
    if not _accepts_pattern(pattern):
        raise ValueError(
            "A multi-file table needs a URI that DuckDB writes and Khiops reads "
            "under the same name: 's3://bucket/table/part-*.tsv' or 'gs://...'. "
            "Otherwise use a path without '*'."
        )
    if sorted_export:
        raise ValueError(
            "A table sorted by its dictionary key is a single file. Remove '*' "
            "from output_data_table_path, or export without a dictionary."
        )
    directory, _, filename = pattern.rpartition("/")
    stem, _, extension = filename.partition("*")
    if (
        "*" in directory
        or "*" in extension
        or len(extension) < 2
        or not extension.startswith(".")
        or "{" in filename
        or "}" in filename
    ):
        raise ValueError(
            "A multi-file output_data_table_path must end with a file name "
            "containing one '*' and an extension, such as 'part-*.tsv'."
        )
    relation.query(
        _VIEW,
        f"COPY {_VIEW} TO {_literal(directory)} (FORMAT csv, DELIMITER '\t', "
        "HEADER true, QUOTE '\"', ESCAPE '\"', PER_THREAD_OUTPUT true, "
        f"FILENAME_PATTERN {_literal(stem + '{i}')}, "
        f"FILE_EXTENSION {_literal(extension[1:])})",
    )


def _accepts_pattern(path: str) -> bool:
    return path.startswith(_PATTERN_SCHEMES)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
