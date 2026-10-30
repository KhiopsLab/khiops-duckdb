"""Inférence des types et validation du schéma."""

import pytest

from khiops_duckdb import Table, materialize


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("1::TINYINT", "Numerical"),
        ("1::SMALLINT", "Numerical"),
        ("1::INTEGER", "Numerical"),
        ("1::BIGINT", "Numerical"),
        ("1::HUGEINT", "Numerical"),
        ("1::UTINYINT", "Numerical"),
        ("1::USMALLINT", "Numerical"),
        ("1::UINTEGER", "Numerical"),
        ("1::UBIGINT", "Numerical"),
        ("1::UHUGEINT", "Numerical"),
        ("1::FLOAT", "Numerical"),
        ("1::DOUBLE", "Numerical"),
        ("1.25::DECIMAL(10,2)", "Numerical"),
        ("true", "Categorical"),
        ("'x'", "Categorical"),
        ("'x'::ENUM('x','y')", "Categorical"),
        ("'550e8400-e29b-41d4-a716-446655440000'::UUID", "Categorical"),
        ("NULL", "Categorical"),
        ("DATE '2026-01-02'", "Date"),
        ("TIME '12:34:56.123'", "Time"),
        ("TIMESTAMP '2026-01-02 12:34:56.123456'", "Timestamp"),
        ("TIMESTAMP_S '2026-01-02 12:34:56'", "Timestamp"),
        ("TIMESTAMP_MS '2026-01-02 12:34:56.123'", "Timestamp"),
        ("TIMESTAMP_NS '2026-01-02 12:34:56.123456789'", "Timestamp"),
        ("TIMESTAMPTZ '2026-01-02 12:34:56+01'", "Timestamp"),
    ],
)
def test_scalar_type_mapping(connection, expression, expected):
    with materialize(connection.sql(f"SELECT {expression} value")) as data:
        variable = data.dictionary_domain.get_dictionary("main_table").get_variable(
            "value"
        )
        assert variable.type == expected


def test_timezone_values_are_normalized_to_utc(connection):
    connection.execute("SET TimeZone = 'Europe/Paris'")
    relation = connection.sql("SELECT TIMESTAMPTZ '2026-01-02 12:34:56+01' value")
    with materialize(relation) as data:
        assert data.to_sklearn()["main_table"][0].value.tolist() == [
            "2026-01-02 11:34:56.000000"
        ]
    assert connection.sql("SELECT current_setting('TimeZone')").fetchall() == [
        ("Europe/Paris",)
    ]


def test_overrides_cast_values_and_define_dictionary_types(connection):
    relation = connection.sql("SELECT 1 id, '2.5' value, [1,2] document")
    table = Table(
        relation,
        key=("id",),
        types={"value": "Numerical", "document": "Text"},
    )
    with materialize(table) as data:
        dictionary = data.dictionary_domain.get_dictionary("main_table")
        assert dictionary.get_variable("id").type == "Categorical"
        assert dictionary.get_variable("value").type == "Numerical"
        assert dictionary.get_variable("document").type == "Text"
        assert data.to_sklearn()["main_table"][0].document.tolist() == ["[1, 2]"]


@pytest.mark.parametrize(
    "expression",
    ["[1,2]", "{'a': 1}", "map(['a'], [1])", "'abc'::BLOB", "INTERVAL '1 day'"],
)
def test_unsupported_types_require_explicit_conversion(connection, expression):
    with pytest.raises(TypeError, match="CAST"):
        Table(connection.sql(f"SELECT {expression} value"))


@pytest.mark.parametrize(
    "sql,key,types,error",
    [
        ("SELECT 1 a", "a", {}, "sequence"),
        ("SELECT 1 a", (1,), {}, "sequence"),
        ("SELECT 1 a", ("a", "a"), {}, "Key columns"),
        ("SELECT 1 a", ("missing",), {}, "Key columns"),
        ("SELECT 1 a", (), {"missing": "Text"}, "existing columns"),
        ("SELECT 1 a", (), {"a": "Unknown"}, "Supported Khiops types"),
        ("SELECT 1 a", ("a",), {"a": "Numerical"}, "Categorical"),
        ('SELECT 1 AS "line\nbreak"', (), {}, "single-line"),
        ('SELECT 1 AS "x", 2 AS "X"', (), {}, "unique"),
    ],
)
def test_invalid_schema(connection, sql, key, types, error):
    with pytest.raises((TypeError, ValueError), match=error):
        Table(connection.sql(sql), key=key, types=types)


def test_non_relation_is_rejected():
    with pytest.raises(TypeError, match="DuckDBPyRelation"):
        Table("SELECT 1")


def test_entity_flag_must_be_boolean(connection):
    with pytest.raises(TypeError, match="boolean"):
        Table(connection.sql("SELECT 1 a"), entity="yes")
