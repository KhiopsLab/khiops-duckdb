"""Data table export: format, values, key order and multiple files."""

import csv
import logging
from pathlib import Path

import duckdb
import khiops.core as kh
import pytest

from khiops_duckdb import build_dictionary_from_relation, export_data_table


def read_rows(path: Path | str) -> list[list[str]]:
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream, delimiter="\t"))


def test_export_writes_tab_separated_text_with_header(connection, tmp_path):
    relation = connection.sql("SELECT * FROM (VALUES (1, 'a'), (2, NULL)) t(n, s)")
    path = tmp_path / "table.tsv"

    result = export_data_table(relation, path)

    assert result == str(path)
    assert path.read_bytes() == b'n\ts\n1\ta\n2\t""\n'


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("'a' || chr(10) || 'b'", "a b"),
        ("'a' || chr(13) || chr(10) || 'b'", "a  b"),
        ("'a' || chr(9) || '\"b\"'", 'a\t"b"'),
        ("'é'", "é"),
        ("NULL", ""),
        ("true", "true"),
        ("2.5::DOUBLE", "2.5"),
        ("1.50::DECIMAL(5,2)", "1.50"),
        ("'nan'::DOUBLE", ""),
        ("'-inf'::FLOAT", ""),
        ("[1, 2]", "[1, 2]"),
        ("DATE '2026-01-02'", "2026-01-02"),
        ("DATE '0045-01-02'", "0045-01-02"),
        ("'infinity'::DATE", ""),
        ("TIME '12:34:56.123'", "12:34:56.123"),
        ("TIME '12:34:56'", "12:34:56.000"),
        ("TIMESTAMP '2026-01-02 12:34:56.123456'", "2026-01-02 12:34:56.123"),
        ("TIMESTAMP_S '2026-01-02 12:34:56'", "2026-01-02 12:34:56.000"),
        ("TIMESTAMP_NS '2026-01-02 12:34:56.999999999'", "2026-01-02 12:34:56.999"),
        ("'-infinity'::TIMESTAMP", ""),
        ("TIMESTAMPTZ '2026-01-02 12:34:56+01'", "2026-01-02 11:34:56.000"),
    ],
)
def test_values_are_written_as_khiops_text(connection, tmp_path, expression, expected):
    connection.execute("SET TimeZone = 'Europe/Paris'")
    relation = connection.sql(f"SELECT 'k' AS id, {expression} AS value")

    path = export_data_table(relation, tmp_path / "table.tsv")

    assert read_rows(path) == [["id", "value"], ["k", expected]]


def test_dictionary_key_orders_all_rows(tmp_path):
    with duckdb.connect(config={"threads": 4}) as connection:
        relation = connection.sql(
            "SELECT (i * 7919) % 100003 AS id, i % 3 AS part FROM range(100000) t(i)"
        )
        domain = build_dictionary_from_relation(relation, "Event", key=["part", "id"])

        path = export_data_table(relation, tmp_path / "sorted.tsv", domain, "Event")

    rows = read_rows(path)[1:]
    assert len(rows) == 100000
    assert rows == sorted(rows, key=lambda row: (row[1], row[0]))


def test_dictionary_key_is_sorted_in_binary_text_order(connection, tmp_path):
    relation = connection.sql(
        "SELECT * FROM (VALUES ('b'), ('2'), ('é'), ('B'), ('10')) t(id)"
    )
    domain = build_dictionary_from_relation(relation, "Customer", key=["id"])

    path = export_data_table(relation, tmp_path / "sorted.tsv", domain, "Customer")

    assert [row[0] for row in read_rows(path)[1:]] == ["10", "2", "B", "b", "é"]


@pytest.mark.integration
@pytest.mark.parametrize("as_path", [str, Path])
def test_dictionary_file_gives_the_key_of_the_named_dictionary(
    connection, tmp_path, as_path
):
    customers = connection.sql("SELECT * FROM (VALUES (2), (10), (1)) t(id)")
    orders = connection.sql("SELECT * FROM (VALUES (2, 1), (10, 2), (10, 1)) t(id, n)")
    domain = build_dictionary_from_relation(customers, "Customer", key=["id"])
    build_dictionary_from_relation(
        orders,
        "Order",
        key=["id", "n"],
        dictionary_domain=domain,
        parent_dictionary_name="Customer",
    )
    dictionary_file_path = tmp_path / "schema.kdic"
    domain.export_khiops_dictionary_file(str(dictionary_file_path))

    path = export_data_table(
        orders, tmp_path / "orders.tsv", as_path(dictionary_file_path), "Order"
    )

    assert read_rows(path)[1:] == [["10", "1"], ["10", "2"], ["2", "1"]]


def test_dictionary_without_key_keeps_the_relation_order(connection, tmp_path):
    relation = connection.sql("SELECT * FROM (VALUES (2), (10), (1)) t(id)")
    domain = build_dictionary_from_relation(relation, "Customer")

    path = export_data_table(relation, tmp_path / "table.tsv", domain, "Customer")

    assert read_rows(path)[1:] == [["2"], ["10"], ["1"]]


def test_cloud_pattern_writes_parts_that_each_repeat_the_header(tmp_path, monkeypatch):
    monkeypatch.setattr("khiops_duckdb.export._accepts_pattern", lambda path: True)
    pattern = f"{tmp_path.as_posix()}/parts/part-*.tsv"
    with duckdb.connect(config={"threads": 4}) as connection:
        connection.execute(
            "CREATE TABLE source AS SELECT i AS id, "
            "CASE WHEN i % 2 = 0 THEN 'a' || chr(10) || '\"b\"' END AS note "
            "FROM range(400000) t(i)"
        )

        result = export_data_table(connection.table("source"), pattern)

    parts = [read_rows(path) for path in (tmp_path / "parts").glob("part-*.tsv")]
    assert result == pattern
    assert parts and all(part[0] == ["id", "note"] for part in parts)
    assert sorted((int(id), note) for part in parts for id, note in part[1:]) == [
        (i, 'a "b"' if i % 2 == 0 else "") for i in range(400000)
    ]


def test_cloud_pattern_refuses_a_folder_that_already_has_parts(
    connection, tmp_path, monkeypatch
):
    monkeypatch.setattr("khiops_duckdb.export._accepts_pattern", lambda path: True)
    pattern = f"{tmp_path.as_posix()}/parts/part-*.tsv"
    relation = connection.sql("SELECT 1 AS id")
    export_data_table(relation, pattern)

    with pytest.raises(duckdb.Error, match="not empty"):
        export_data_table(relation, pattern)


@pytest.mark.parametrize(
    "output_data_table_path,key,error",
    [
        ("parts/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("C:/data/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("file:///data/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("gcs://bucket/table/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("az://container/table/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("https://host/table/part-*.tsv", (), "DuckDB writes and Khiops reads"),
        ("gs://bucket/table/part-*.tsv", ("id",), "single file"),
        ("s3://bucket/table/part-*.tsv", ("id",), "single file"),
        ("s3://bucket/*/part.tsv", (), "one '\\*' and an extension"),
        ("s3://bucket/table/part-*", (), "one '\\*' and an extension"),
        ("s3://bucket/table/*-*.tsv", (), "one '\\*' and an extension"),
        ("", (), "cannot be empty"),
    ],
)
def test_invalid_output_path_is_rejected_before_writing(
    connection, output_data_table_path, key, error
):
    relation = connection.sql("SELECT 1 AS id")
    domain = build_dictionary_from_relation(relation, "Customer", key=key)

    with pytest.raises(ValueError, match=error):
        export_data_table(relation, output_data_table_path, domain, "Customer")


@pytest.mark.parametrize(
    "dictionary,dictionary_name,error",
    [
        (None, "Customer", "requires dictionary_file_path_or_domain"),
        ("domain", None, "dictionary_name is required"),
        ("domain", "", "dictionary_name is required"),
        ("domain", "Missing", "No dictionary named 'Missing'"),
        ("domain", "Order", "Key variables \\['order_id'\\]"),
        (123, "Customer", "dictionary file path or a DictionaryDomain"),
    ],
)
def test_invalid_dictionary_is_rejected(
    connection, tmp_path, dictionary, dictionary_name, error
):
    relation = connection.sql("SELECT 1 AS id")
    domain = build_dictionary_from_relation(relation, "Customer", key=["id"])
    build_dictionary_from_relation(
        connection.sql("SELECT 1 AS id, 1 AS order_id"),
        "Order",
        key=["id", "order_id"],
        dictionary_domain=domain,
        parent_dictionary_name="Customer",
    )
    if dictionary == "domain":
        dictionary = domain

    with pytest.raises((TypeError, ValueError), match=error):
        export_data_table(relation, tmp_path / "table.tsv", dictionary, dictionary_name)

    assert not (tmp_path / "table.tsv").exists()


@pytest.mark.parametrize(
    "column,declared",
    [
        ("TIMESTAMP '2026-01-02 12:34:56'", "Date"),
        ("DATE '2026-01-02'", "Numerical"),
        ("true", "Numerical"),
    ],
)
def test_column_the_dictionary_cannot_read_is_rejected_before_writing(
    connection, tmp_path, column, declared
):
    described = connection.sql("SELECT 1 AS id, 'text' AS value")
    domain = build_dictionary_from_relation(
        described, "Event", variable_types={"value": declared}
    )
    relation = connection.sql(f"SELECT 1 AS id, {column} AS value")

    with pytest.raises(
        TypeError, match=f"'value'.*cannot be read by Khiops as {declared}"
    ):
        export_data_table(relation, tmp_path / "table.tsv", domain, "Event")

    assert not (tmp_path / "table.tsv").exists()


def described_as(kind: str, khiops_format: str | None) -> kh.DictionaryDomain:
    dictionary = kh.Dictionary()
    dictionary.name = "Event"
    dictionary.add_variable_from_spec(name="id", type="Categorical")
    meta_data = {f"{kind}Format": khiops_format} if khiops_format else None
    dictionary.add_variable_from_spec(name="value", type=kind, meta_data=meta_data)
    domain = kh.DictionaryDomain()
    domain.add_dictionary(dictionary)
    return domain


@pytest.mark.parametrize(
    "expression,kind,khiops_format,expected",
    [
        ("DATE '2026-03-04'", "Date", "DD/MM/YYYY", "04/03/2026"),
        ("DATE '2026-03-04'", "Date", "YYYYDDMM", "20260403"),
        ("DATE '2026-03-04'", "Date", "MM.DD.YYYY", "03.04.2026"),
        ("TIME '05:06:07.089'", "Time", "HH:MM:SS", "05:06:07"),
        ("TIME '05:06:07.089'", "Time", "(H)H:(M)M:(S)S", "5:6:7"),
        ("TIME '05:06:07.089'", "Time", "HH.MM.SS.", "05.06.07.089"),
        ("TIME '05:06:07.089'", "Time", "HHMM", "0506"),
        (
            "TIMESTAMP '2026-03-04 05:06:07.089'",
            "Timestamp",
            None,
            "2026-03-04 05:06:07.089",
        ),
        (
            "TIMESTAMP '2026-03-04 05:06:07.089'",
            "Timestamp",
            "DD.MM.YYYYTHH:MM",
            "04.03.2026T05:06",
        ),
        (
            "TIMESTAMP '2026-03-04 05:06:07.089'",
            "Timestamp",
            "YYYYMMDDHHMMSS.",
            "20260304050607.089",
        ),
        (
            "TIMESTAMP '2026-03-04 05:06:07.089'",
            "Timestamp",
            "YYYY-MM-DD-HH:MM:SS",
            "2026-03-04-05:06:07",
        ),
        (
            "TIMESTAMPTZ '2026-03-04 05:06:07.089+01'",
            "Timestamp",
            "YYYY/MM/DD_HH:MM:SS.",
            "2026/03/04_04:06:07.089",
        ),
        (
            "TIMESTAMPTZ '2026-03-04 05:06:07.089+01'",
            "TimestampTZ",
            None,
            "2026-03-04 04:06:07.089+00:00",
        ),
        (
            "TIMESTAMPTZ '2026-03-04 05:06:07.089+01'",
            "TimestampTZ",
            "DD/MM/YYYY HH:MM:SSzzzzz",
            "04/03/2026 04:06:07+0000",
        ),
        ("'04|03|2026'", "Date", "any text is left as it is", "04|03|2026"),
    ],
)
def test_dates_and_times_follow_the_format_the_dictionary_declares(
    connection, tmp_path, expression, kind, khiops_format, expected
):
    connection.execute("SET TimeZone = 'Europe/Paris'")
    relation = connection.sql(f"SELECT 'k' AS id, {expression} AS value")
    domain = described_as(kind, khiops_format)

    path = export_data_table(relation, tmp_path / "table.tsv", domain, "Event")

    assert read_rows(path) == [["id", "value"], ["k", expected]]


@pytest.mark.parametrize(
    "expression,kind,khiops_format",
    [
        ("DATE '2026-03-04'", "Date", "YYYY MM DD"),
        ("TIME '05:06:07'", "Time", "HH-MM-SS"),
        ("TIMESTAMP '2026-03-04 05:06:07'", "Timestamp", "YYYY-MM-DDHH:MM:SS"),
        ("TIMESTAMPTZ '2026-03-04 05:06:07+01'", "TimestampTZ", "YYYY-MM-DD HH:MM:SS"),
    ],
)
def test_format_khiops_does_not_know_is_rejected_before_writing(
    connection, tmp_path, expression, kind, khiops_format
):
    relation = connection.sql(f"SELECT 'k' AS id, {expression} AS value")
    domain = described_as(kind, khiops_format)

    with pytest.raises(ValueError, match=f"'value'.*not a Khiops {kind} format"):
        export_data_table(relation, tmp_path / "table.tsv", domain, "Event")

    assert not (tmp_path / "table.tsv").exists()


def test_differences_between_relation_and_dictionary_are_logged(
    connection, tmp_path, caplog
):
    described = connection.sql("SELECT 1 AS id, 'yes' AS churn, 2.5 AS amount")
    domain = build_dictionary_from_relation(described, "Customer")
    relation = connection.sql("SELECT 1 AS id, 2.5 AS amount, 3 AS brand_new")
    caplog.set_level(logging.INFO, logger="khiops_duckdb")

    export_data_table(relation, tmp_path / "table.tsv", domain, "Customer")

    messages = {record.levelname: record.getMessage() for record in caplog.records}
    assert "['brand_new']" in messages["INFO"] and "not exported" in messages["INFO"]
    assert "['churn']" in messages["WARNING"] and "'Customer'" in messages["WARNING"]


def test_relation_matching_its_dictionary_logs_nothing(connection, tmp_path, caplog):
    relation = connection.sql("SELECT 1 AS id, 2.5 AS amount")
    domain = build_dictionary_from_relation(relation, "Customer")
    caplog.set_level(logging.INFO, logger="khiops_duckdb")

    export_data_table(relation, tmp_path / "table.tsv", domain, "Customer")

    assert caplog.records == []


def test_dictionary_selects_the_columns_it_stores(connection, tmp_path):
    described = connection.sql("SELECT 1 AS id, 'yes' AS churn, 2.5 AS amount")
    domain = build_dictionary_from_relation(described, "Customer", key=["id"])
    dictionary = domain.get_dictionary("Customer")
    dictionary.get_variable("amount").used = False
    dictionary.add_variable_from_spec(
        name="computed", type="Numerical", rule="Sum(amount, 1)"
    )
    block = kh.VariableBlock()
    block.name = "words"
    block.add_variable(kh.Variable(json_data={"name": "word1", "type": "Numerical"}))
    dictionary.add_variable_block(block)
    relation = connection.sql(
        "SELECT 1 AS id, 2.5 AS amount, true AS computed, 3 AS unknown, "
        "'1:2' AS words, 9 AS word1"
    )

    path = export_data_table(relation, tmp_path / "table.tsv", domain, "Customer")

    assert read_rows(path) == [["id", "amount", "words"], ["1", "2.5", "1:2"]]


def test_relation_with_no_column_of_the_dictionary_is_rejected(connection, tmp_path):
    domain = build_dictionary_from_relation(connection.sql("SELECT 1 AS id"), "Other")
    relation = connection.sql("SELECT 1 AS customer_id")

    with pytest.raises(ValueError, match="No column of the relation.*'Other'"):
        export_data_table(relation, tmp_path / "table.tsv", domain, "Other")


@pytest.mark.parametrize(
    "sql,error",
    [
        ('SELECT 1 AS "line\nbreak"', "single-line"),
        ('SELECT 1 AS "x", 2 AS "X"', "unique"),
    ],
)
def test_invalid_column_names_are_rejected(connection, tmp_path, sql, error):
    relation = connection.sql(sql)

    with pytest.raises(ValueError, match=error):
        export_data_table(relation, tmp_path / "table.tsv")


def test_non_relation_is_rejected(tmp_path):
    with pytest.raises(TypeError, match="DuckDBPyRelation"):
        export_data_table("SELECT 1", tmp_path / "table.tsv")
