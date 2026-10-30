"""Contrats des fichiers, types, clés et durées de vie."""

import csv
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from khiops_duckdb import Table, materialize


def read_rows(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as stream:
        return list(csv.reader(stream, delimiter="\t"))


def test_plain_relation_and_native_core_arguments(connection):
    with materialize(connection.sql("SELECT 1 AS value")) as data:
        assert read_rows(data.data_table_path) == [["value"], ["1"]]
        assert data.dictionary_name == "main_table"
        assert (
            data.core_args["dictionary_file_path_or_domain"] is data.dictionary_domain
        )
        assert data.table_args == {
            "data_table_path": data.data_table_path,
            "additional_data_tables": {},
            "header_line": True,
            "field_separator": "\t",
        }


def test_cleanup_preserves_parent_directory(connection, tmp_path):
    parent = tmp_path / "space's directory"
    parent.mkdir()
    sentinel = parent / "keep.txt"
    sentinel.write_text("keep")
    with materialize(connection.sql("SELECT 1 a"), directory=parent) as data:
        exported = Path(data.data_table_path)
        assert exported.parent.parent == parent
    assert not exported.parent.exists()
    assert list(parent.iterdir()) == [sentinel]


def test_cleanup_on_caller_exception(connection, tmp_path):
    with pytest.raises(RuntimeError, match="caller"):
        with materialize(connection.sql("SELECT 1 a"), directory=tmp_path):
            raise RuntimeError("caller")
    assert list(tmp_path.iterdir()) == []


def test_cleanup_when_secondary_export_fails(connection, tmp_path):
    main = Table(connection.sql("SELECT 'a' id"), key=("id",))
    child = Table(connection.sql("SELECT NULL::VARCHAR id"), key=("id",))
    with pytest.raises(ValueError, match="missing"):
        with materialize(main, additional_tables={"child": child}, directory=tmp_path):
            pytest.fail("Invalid keys must fail before yielding.")
    assert list(tmp_path.iterdir()) == []


def test_source_failure_propagates_and_removes_snapshot(connection, tmp_path):
    source = tmp_path / "source.parquet"
    connection.sql("SELECT 1 n").write_parquet(str(source))
    relation = connection.read_parquet(str(source))
    source.unlink()
    with pytest.raises(duckdb.Error):
        with materialize(relation, directory=tmp_path):
            pytest.fail("Missing source must not produce a dataset.")
    assert list(tmp_path.iterdir()) == []


def test_key_sort_is_lexical_and_ignores_connection_collation(connection):
    connection.execute("SET default_collation = 'nocase'")
    relation = connection.sql(
        "SELECT * FROM (VALUES ('2'), ('10'), ('B'), ('a'), ('001')) source(id)"
    )
    with materialize(Table(relation, key=("id",))) as data:
        assert read_rows(data.data_table_path)[1:] == [
            ["001"],
            ["10"],
            ["2"],
            ["B"],
            ["a"],
        ]
    assert connection.sql("SELECT current_setting('default_collation')").fetchall() == [
        ("nocase",)
    ]


def test_text_quoting_unicode_and_newlines_preserve_source(connection):
    text = 'été\t"quoted"\r\nsecond'
    relation = connection.sql('SELECT ? AS "a""b"', params=[text])
    with materialize(relation) as data:
        assert read_rows(data.data_table_path) == [
            ['a"b'],
            ['été\t"quoted"  second'],
        ]
    assert relation.fetchall() == [(text,)]


def test_nulls_empty_and_literal_na_strings(connection):
    relation = connection.sql(
        "SELECT * FROM (VALUES (NULL, NULL), ('NA', 2.5), ('', 0)) source(s, n)"
    )
    with materialize(relation) as data:
        frame = data.to_sklearn()["main_table"][0]
        assert frame.s.tolist() == ["", "NA", ""]
        assert pd.isna(frame.n.iloc[0])
        assert frame.n.iloc[1:].tolist() == [2.5, 0.0]


def test_empty_relation_preserves_schema(connection):
    with materialize(connection.sql("SELECT 1 n, 'x' s WHERE false")) as data:
        assert read_rows(data.data_table_path) == [["n", "s"]]
        assert data.to_sklearn()["main_table"][0].empty


@pytest.mark.parametrize("sql", ["SELECT NULL::DOUBLE n", "SELECT NULL::VARCHAR s"])
def test_single_missing_record_is_not_dropped(connection, sql):
    with materialize(connection.sql(sql)) as data:
        assert len(read_rows(data.data_table_path)) == 2
        assert len(data.to_sklearn()["main_table"][0]) == 1


def test_monotable_sklearn_spec_omits_multitable_field(connection):
    with materialize(connection.sql("SELECT 1 n")) as data:
        assert set(data.to_sklearn()) == {"main_table"}


def test_source_is_evaluated_once_even_with_validation_and_sklearn(connection):
    connection.execute("CREATE SEQUENCE sequence")
    relation = connection.sql("SELECT nextval('sequence') id FROM range(5)")
    with materialize(Table(relation, key=("id",))) as data:
        data.to_sklearn()
        data.to_sklearn()
    assert connection.sql("SELECT currval('sequence')").fetchall() == [(5,)]


def test_sklearn_frames_are_independent_and_outlive_context(connection):
    relation = connection.sql("SELECT '001' id, 1 value")
    with materialize(Table(relation, key=("id",))) as data:
        first = data.to_sklearn()
        first["main_table"][0].loc[0, "value"] = 9
        second = data.to_sklearn()
    assert second["main_table"][0].id.tolist() == ["001"]
    assert second["main_table"][0].value.tolist() == [1.0]


def test_nested_tables_and_entities_in_any_mapping_order(connection):
    root = Table(connection.sql("SELECT 'c1' id"), key=("id",))
    orders = Table(
        connection.sql("SELECT 'c1' id, '2' order_id"), key=("id", "order_id")
    )
    items = Table(
        connection.sql("SELECT 'c1' id, '2' order_id, 3 amount"),
        key=("id", "order_id"),
    )
    profile = Table(connection.sql("SELECT 'c1' id, 20 age"), key=("id",), entity=True)
    with materialize(
        root,
        additional_tables={"orders/items": items, "profile": profile, "orders": orders},
    ) as data:
        domain = data.dictionary_domain
        assert domain.get_dictionary("main_table").root
        assert (
            domain.get_dictionary("main_table").get_variable("profile").type == "Entity"
        )
        assert (
            domain.get_dictionary("orders").get_variable("items").object_type == "items"
        )
        assert set(data.additional_data_tables) == {"orders/items", "profile", "orders"}
        spec = data.to_sklearn()
        assert spec["main_table"][1] == ["id"]
        assert spec["additional_data_tables"]["profile"][2] is True
        assert spec["additional_data_tables"]["orders/items"][1] == ["id", "order_id"]


@pytest.mark.parametrize("key", ["001", "True", "NA"])
def test_sklearn_rejects_keys_reinterpreted_by_upstream(connection, key):
    root = Table(connection.sql("SELECT ? id", params=[key]), key=("id",))
    with materialize(root, additional_tables={"child": root}) as data:
        with pytest.raises(ValueError, match="Khiops 11 re-infers"):
            data.to_sklearn()


@pytest.mark.parametrize("value", [None, "", "line\nbreak", "line\rbreak"])
def test_missing_or_multiline_keys_are_rejected(connection, value):
    relation = connection.sql("SELECT ?::VARCHAR id", params=[value])
    with pytest.raises(ValueError, match="missing or multiline"):
        with materialize(Table(relation, key=("id",))):
            pytest.fail("Invalid key accepted.")


@pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
def test_nonfinite_numbers_are_rejected(connection, value):
    with pytest.raises(ValueError, match="NaN or infinity"):
        with materialize(connection.sql("SELECT ?::DOUBLE n", params=[value])):
            pytest.fail("Non-finite number accepted.")


def test_duplicate_composite_main_key_is_rejected(connection):
    relation = connection.sql(
        "SELECT * FROM (VALUES ('1', 'a'), ('1', 'a')) source(id, part)"
    )
    with pytest.raises(ValueError, match="unique"):
        with materialize(Table(relation, key=("id", "part"))):
            pytest.fail("Duplicate main key accepted.")


def test_repeated_child_keys_are_allowed_but_entity_keys_are_unique(connection):
    root = Table(connection.sql("SELECT '1' id"), key=("id",))
    relation = connection.sql("SELECT '1' id FROM range(2)")
    with materialize(root, additional_tables={"child": Table(relation, key=("id",))}):
        pass
    with pytest.raises(ValueError, match="unique"):
        with materialize(
            root, additional_tables={"child": Table(relation, key=("id",), entity=True)}
        ):
            pytest.fail("Duplicate entity key accepted.")


@pytest.mark.parametrize(
    "path,root_key,child_key,entity,error",
    [
        ("", ("id",), ("id",), False, "path"),
        ("../child", ("id",), ("id",), False, "path"),
        ("/child", ("id",), ("id",), False, "path"),
        ("child/", ("id",), ("id",), False, "path"),
        ("absent/child", ("id",), ("id",), False, "parent"),
        ("child", (), ("id",), False, "key"),
        ("child", ("id",), (), False, "key"),
        ("child", ("id",), ("other",), False, "start"),
        ("child", ("id",), ("id", "other"), True, "exactly"),
        ("main_table", ("id",), ("id",), False, "unique"),
        ("value", ("id",), ("id",), False, "conflicts"),
    ],
)
def test_invalid_hierarchies_fail_before_export(
    connection, path, root_key, child_key, entity, error
):
    relation = connection.sql("SELECT '1' id, '2' other, 3 value")
    with pytest.raises(ValueError, match=error):
        with materialize(
            Table(relation, key=root_key),
            additional_tables={path: Table(relation, key=child_key, entity=entity)},
        ):
            pytest.fail("Invalid hierarchy accepted.")


def test_repeated_leaf_names_are_rejected(connection):
    table = Table(connection.sql("SELECT '1' id"), key=("id",))
    with pytest.raises(ValueError, match="globally unique"):
        with materialize(
            table,
            additional_tables={"a": table, "b": table, "a/x": table, "b/x": table},
        ):
            pytest.fail("Duplicate dictionary names accepted.")


def test_main_table_cannot_be_an_entity(connection):
    with pytest.raises(ValueError, match="main table"):
        with materialize(Table(connection.sql("SELECT '1' id"), entity=True)):
            pytest.fail("Main table entity accepted.")


def test_additional_tables_require_table_instances(connection):
    with pytest.raises(TypeError, match="Table instances"):
        with materialize(
            connection.sql("SELECT 1 a"),
            additional_tables={"child": connection.sql("SELECT 1 a")},
        ):
            pytest.fail("Bare secondary relation accepted.")
