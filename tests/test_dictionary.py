"""Khiops dictionaries: inferred types, keys and table links."""

import pytest

from khiops_duckdb import build_dictionary_from_relation


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
def test_duckdb_types_map_to_khiops_types(connection, expression, expected):
    relation = connection.sql(f"SELECT {expression} AS value")

    domain = build_dictionary_from_relation(relation, "Table")

    assert domain.get_dictionary("Table").get_variable("value").type == expected


def test_key_columns_are_categorical_and_variable_types_relabel_columns(connection):
    relation = connection.sql("SELECT 1 AS id, '2.5' AS value, [1, 2] AS document")

    domain = build_dictionary_from_relation(
        relation,
        "Customer",
        key=["id"],
        variable_types={"value": "Numerical", "document": "Text"},
    )

    dictionary = domain.get_dictionary("Customer")
    assert dictionary.key == ["id"]
    assert not dictionary.root
    assert [(variable.name, variable.type) for variable in dictionary.variables] == [
        ("id", "Categorical"),
        ("value", "Numerical"),
        ("document", "Text"),
    ]


def test_temporal_variables_declare_the_exported_format(connection):
    relation = connection.sql(
        "SELECT TIME '12:34:56' AS t, TIMESTAMP '2026-01-02 12:34:56' AS ts"
    )

    domain = build_dictionary_from_relation(relation, "Event")

    dictionary = domain.get_dictionary("Event")
    assert dictionary.get_variable("t").meta_data.get_value("TimeFormat") == "HH:MM:SS."
    assert (
        dictionary.get_variable("ts").meta_data.get_value("TimestampFormat")
        == "YYYY-MM-DD HH:MM:SS."
    )


@pytest.mark.parametrize(
    "expression",
    ["[1,2]", "{'a': 1}", "map(['a'], [1])", "'abc'::BLOB", "INTERVAL '1 day'"],
)
def test_unsupported_types_require_a_cast_or_a_variable_type(connection, expression):
    relation = connection.sql(f"SELECT {expression} AS value")

    with pytest.raises(TypeError, match="CAST"):
        build_dictionary_from_relation(relation, "Table")


@pytest.mark.parametrize(
    "expression,variable_type",
    [
        ("TIMESTAMP '2026-01-02 12:34:56'", "Date"),
        ("DATE '2026-01-02'", "Timestamp"),
        ("TIME '12:34:56'", "Numerical"),
        ("1::INTEGER", "Date"),
        ("true", "Numerical"),
        ("[1, 2]", "Numerical"),
        ("TIMESTAMP '2026-01-02 12:34:56'", "TimestampTZ"),
    ],
)
def test_variable_type_the_export_cannot_satisfy_is_rejected(
    connection, expression, variable_type
):
    relation = connection.sql(f"SELECT {expression} AS value")

    with pytest.raises(TypeError, match=f"cannot be read by Khiops as {variable_type}"):
        build_dictionary_from_relation(
            relation, "Table", variable_types={"value": variable_type}
        )


@pytest.mark.parametrize(
    "expression,variable_type",
    [
        ("'2.5'", "Numerical"),
        ("'2026-01-02'", "Date"),
        ("'x'::ENUM('x','y')", "Timestamp"),
        ("NULL", "Numerical"),
        ("1::INTEGER", "Categorical"),
        ("TIMESTAMPTZ '2026-01-02 12:34:56+01'", "Timestamp"),
        ("TIMESTAMPTZ '2026-01-02 12:34:56+01'", "TimestampTZ"),
        ("INTERVAL '1 day'", "Text"),
    ],
)
def test_variable_type_is_accepted_for_text_and_matching_columns(
    connection, expression, variable_type
):
    relation = connection.sql(f"SELECT {expression} AS value")

    domain = build_dictionary_from_relation(
        relation, "Table", variable_types={"value": variable_type}
    )

    assert domain.get_dictionary("Table").get_variable("value").type == variable_type


def test_tables_are_linked_to_their_parent_in_one_domain(connection):
    customers = connection.sql("SELECT 1 AS id, 'yes' AS churn")
    orders = connection.sql("SELECT 1 AS id, 1 AS order_id, 2.5 AS amount")
    lines = connection.sql("SELECT 1 AS id, 1 AS order_id, 1 AS line_id")
    address = connection.sql("SELECT 1 AS id, 'Paris' AS city")
    domain = build_dictionary_from_relation(customers, "Customer", key=["id"])

    build_dictionary_from_relation(
        orders,
        "Order",
        key=["id", "order_id"],
        dictionary_domain=domain,
        parent_dictionary_name="Customer",
    )
    build_dictionary_from_relation(
        lines,
        "Line",
        key=["id", "order_id", "line_id"],
        dictionary_domain=domain,
        parent_dictionary_name="Order",
    )
    result = build_dictionary_from_relation(
        address,
        "Address",
        key=["id"],
        dictionary_domain=domain,
        parent_dictionary_name="Customer",
        entity=True,
    )

    assert result is domain
    assert [
        (dictionary.name, dictionary.root) for dictionary in domain.dictionaries
    ] == [
        ("Customer", True),
        ("Order", False),
        ("Line", False),
        ("Address", False),
    ]
    customer = domain.get_dictionary("Customer")
    links = [variable for variable in customer.variables if variable.object_type]
    assert [(link.name, link.type, link.object_type) for link in links] == [
        ("Order", "Table", "Order"),
        ("Address", "Entity", "Address"),
    ]
    assert domain.extract_data_paths("Customer") == ["Order", "Order/Line", "Address"]


@pytest.mark.parametrize(
    "dictionary_name,arguments,error",
    [
        ("Order", {"key": ["order_id"], "parent_dictionary_name": "Customer"}, "start"),
        ("Order", {"key": [], "parent_dictionary_name": "Customer"}, "must start"),
        ("Order", {"key": ["id"], "parent_dictionary_name": "Log"}, "must start"),
        ("Order", {"key": ["id"], "parent_dictionary_name": "Missing"}, "Unknown"),
        ("Order", {"key": ["id"], "entity": True}, "requires parent_dictionary_name"),
        (
            "Order",
            {"key": ["id", "order_id"], "parent_dictionary_name": "Customer"}
            | {"entity": True},
            "exactly the key",
        ),
        ("Customer", {"key": ["id"], "parent_dictionary_name": "Customer"}, "already"),
        ("churn", {"key": ["id"], "parent_dictionary_name": "Customer"}, "conflicts"),
        ("", {"key": ["id"], "parent_dictionary_name": "Customer"}, "nonempty"),
        (
            "Order",
            {"key": ["id"], "parent_dictionary_name": "Customer", "entity": 1},
            "boolean",
        ),
    ],
)
def test_invalid_table_link_leaves_the_domain_unchanged(
    connection, dictionary_name, arguments, error
):
    domain = build_dictionary_from_relation(
        connection.sql("SELECT 1 AS id, 'yes' AS churn"), "Customer", key=["id"]
    )
    build_dictionary_from_relation(
        connection.sql("SELECT 1 AS id"), "Log", dictionary_domain=domain
    )
    orders = connection.sql("SELECT 1 AS id, 1 AS order_id")

    with pytest.raises((TypeError, ValueError), match=error):
        build_dictionary_from_relation(
            orders, dictionary_name, dictionary_domain=domain, **arguments
        )

    assert [dictionary.name for dictionary in domain.dictionaries] == [
        "Customer",
        "Log",
    ]
    customer = domain.get_dictionary("Customer")
    assert [variable.name for variable in customer.variables] == ["id", "churn"]


def test_parent_requires_the_domain_that_contains_it(connection):
    orders = connection.sql("SELECT 1 AS id, 1 AS order_id")

    with pytest.raises(ValueError, match="Unknown parent"):
        build_dictionary_from_relation(
            orders,
            "Order",
            key=["id", "order_id"],
            parent_dictionary_name="Customer",
        )


@pytest.mark.parametrize(
    "sql,key,variable_types,error",
    [
        ("SELECT 1 a", "a", {}, "sequence"),
        ("SELECT 1 a", (1,), {}, "sequence"),
        ("SELECT 1 a", ("a", "a"), {}, "key columns"),
        ("SELECT 1 a", ("missing",), {}, "key columns"),
        ("SELECT 1 a", (), {"missing": "Text"}, "existing columns"),
        ("SELECT 1 a", (), {"a": "Unknown"}, "Supported Khiops types"),
        ("SELECT 1 a", ("a",), {"a": "Numerical"}, "Categorical"),
        ('SELECT 1 AS "line\nbreak"', (), {}, "single-line"),
        ('SELECT 1 AS "x", 2 AS "X"', (), {}, "unique"),
    ],
)
def test_invalid_schema_is_rejected(connection, sql, key, variable_types, error):
    relation = connection.sql(sql)

    with pytest.raises((TypeError, ValueError), match=error):
        build_dictionary_from_relation(
            relation, "Table", key=key, variable_types=variable_types
        )


def test_non_relation_is_rejected():
    with pytest.raises(TypeError, match="DuckDBPyRelation"):
        build_dictionary_from_relation("SELECT 1", "Table")


def build_schema_file(connection, path, **options):
    customers = connection.sql("SELECT 1 AS id, 'yes' AS churn, 2.5 AS amount")
    orders = connection.sql("SELECT 1 AS id, 1 AS order_id")
    build_dictionary_from_relation(
        customers, "Customer", key=["id"], output_dictionary_file_path=path, **options
    )
    return build_dictionary_from_relation(
        orders,
        "Order",
        key=["id", "order_id"],
        parent_dictionary_name="Customer",
        output_dictionary_file_path=path,
    )


def hand_edit(path):
    text = path.read_text()
    text = text.replace("\tNumerical\tamount\t", "Unused\tNumerical\tamount\t")
    path.write_text(text.replace("Table(Order)\tOrder\t", "Table(Order)\tOrders\t"))


@pytest.mark.integration
def test_dictionary_file_is_written_once_and_hand_edits_are_kept(connection, tmp_path):
    path = tmp_path / "schema.kdic"
    build_schema_file(connection, path)
    hand_edit(path)
    edited = path.read_text()

    domain = build_schema_file(connection, path)

    assert path.read_text() == edited
    assert not domain.get_dictionary("Customer").get_variable("amount").used
    assert domain.extract_data_paths("Customer") == ["Orders"]


@pytest.mark.integration
def test_overwrite_rebuilds_the_dictionary_file_from_the_relations(
    connection, tmp_path
):
    path = tmp_path / "schema.kdic"
    build_schema_file(connection, path)
    hand_edit(path)

    domain = build_schema_file(connection, path, overwrite=True)

    assert domain.get_dictionary("Customer").get_variable("amount").used
    assert domain.extract_data_paths("Customer") == ["Order"]
    assert "Unused" not in path.read_text()


@pytest.mark.integration
@pytest.mark.parametrize(
    "arguments,error",
    [
        ({"overwrite": True}, "overwrite requires output_dictionary_file_path"),
        (
            {"dictionary_domain": "domain", "output_dictionary_file_path": "file"},
            "both",
        ),
        (
            {"output_dictionary_file_path": "file", "overwrite": True}
            | {"parent_dictionary_name": "Customer"},
            "overwrite=True on the table without a parent",
        ),
    ],
)
def test_invalid_file_options_are_rejected(connection, tmp_path, arguments, error):
    path = tmp_path / "schema.kdic"
    domain = build_schema_file(connection, path)
    replacements = {"domain": domain, "file": path}
    arguments = {
        name: replacements.get(value, value) if isinstance(value, str) else value
        for name, value in arguments.items()
    }
    orders = connection.sql("SELECT 1 AS id, 1 AS order_id")

    with pytest.raises(ValueError, match=error):
        build_dictionary_from_relation(
            orders, "Order", key=["id", "order_id"], **arguments
        )
