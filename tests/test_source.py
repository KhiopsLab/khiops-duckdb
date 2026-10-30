"""Résolution des fichiers et des relations pour les API de haut niveau."""

import gzip
from pathlib import Path

import duckdb
import pytest

from khiops_duckdb import Source, Table
from khiops_duckdb.source import _file_format, _materialize_source


@pytest.mark.parametrize(
    ("name", "format"),
    [
        ("data.parquet", "parquet"),
        ("data.pq", "parquet"),
        ("data.CSV.GZ", "csv"),
        ("data.tsv.zst", "csv"),
        ("data.tab", "csv"),
        ("data.txt", "csv"),
        ("data.json", "json"),
        ("data.jsonl", "json"),
        ("data.ndjson", "json"),
        ("part-?.csv", "csv"),
        ("s3://bucket/part-*.parquet", "parquet"),
        ("https://example.test/data.json?download=1", "json"),
        ("C:/data/source.parquet", "parquet"),
    ],
)
def test_file_format_inference(name, format):
    assert _file_format(name) == format


@pytest.mark.parametrize("format", ["parquet", "csv", "tsv", "jsonl", "csv.gz"])
def test_sources_are_read_without_an_explicit_connection(
    training_relation, tmp_path, format
):
    path = tmp_path / f"data.{format}"
    relation = training_relation.project("id, signal, 'class_' || target AS target")
    if format == "parquet":
        relation.write_parquet(str(path))
    elif format == "jsonl":
        relation.df().to_json(path, orient="records", lines=True)
    else:
        contents = relation.df().to_csv(
            index=False, sep="\t" if format == "tsv" else ",", lineterminator="\n"
        )
        if format == "csv.gz":
            with gzip.open(path, "wt") as stream:
                stream.write(contents)
        else:
            path.write_text(contents)

    with _materialize_source(path) as data:
        snapshot = Path(data.data_table_path)
        frame = data.to_sklearn()["main_table"][0]

    assert len(frame) == 80
    assert set(frame.target) == {"class_no", "class_yes"}
    assert not snapshot.exists()


def test_explicit_format_reader_options_and_schema(tmp_path):
    path = tmp_path / "source.data"
    path.write_text("id|body\n001|hello\n002|world\n")
    options = {"delimiter": "|", "header": True, "dtype": {"id": "VARCHAR"}}
    source = Source(
        path,
        format="csv",
        options=options,
        key=("id",),
        types={"body": "Text"},
    )

    with _materialize_source(source) as data:
        dictionary = data.dictionary_domain.get_dictionary("main_table")
        assert dictionary.key == ["id"]
        assert dictionary.get_variable("body").type == "Text"
        assert data.to_sklearn()["main_table"][0].id.tolist() == ["001", "002"]

    assert options == {"delimiter": "|", "header": True, "dtype": {"id": "VARCHAR"}}


def test_sources_can_mix_files_relations_and_existing_tables(connection, tmp_path):
    path = tmp_path / "orders.parquet"
    connection.sql("SELECT 'c1' id, 'o1' order_id").write_parquet(str(path))
    root = Table(connection.sql("SELECT 'c1' id"), key=("id",))
    profile = Source(
        connection.sql("SELECT 'c1' id, 'west' region"),
        key=("id",),
        entity=True,
    )

    with _materialize_source(
        root,
        additional_tables={
            "orders": Source(path, key=("id", "order_id")),
            "profile": profile,
        },
        connection=connection,
    ) as data:
        assert set(data.additional_data_tables) == {"orders", "profile"}
        assert data.to_sklearn()["additional_data_tables"]["profile"][2] is True

    assert connection.sql("SELECT 1").fetchall() == [(1,)]


@pytest.mark.parametrize(
    ("source", "error", "match"),
    [
        ("", ValueError, "empty"),
        ("database.duckdb", ValueError, "Cannot infer"),
        (42, TypeError, "Sources must be"),
        (Source("data.csv", format="xml"), ValueError, "format must be"),
    ],
)
def test_invalid_sources_raise_explicit_errors(source, error, match):
    with pytest.raises(error, match=match), _materialize_source(source):
        pytest.fail("Invalid sources must not yield a dataset.")


@pytest.mark.parametrize("option", [{"format": "csv"}, {"options": {"header": True}}])
def test_reader_options_on_relations_are_rejected(connection, option):
    with (
        pytest.raises(ValueError, match="cannot apply to a relation"),
        _materialize_source(Source(connection.sql("SELECT 1 n"), **option)),
    ):
        pytest.fail("Reader options must not be silently ignored.")


def test_empty_secondary_table_path_is_rejected(training_relation):
    with (
        pytest.raises(ValueError, match="cannot be empty"),
        _materialize_source(
            training_relation, additional_tables={"": training_relation}
        ),
    ):
        pytest.fail("The main source must not be replaced.")


def test_owned_connections_close_when_file_reading_fails(monkeypatch, tmp_path):
    opened = []
    connect = duckdb.connect

    def track_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        opened.append(connection)
        return connection

    monkeypatch.setattr(duckdb, "connect", track_connection)
    with (
        pytest.raises(duckdb.IOException),
        _materialize_source(tmp_path / "missing.parquet"),
    ):
        pytest.fail("A missing source must raise.")

    assert opened
    for connection in opened:
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")


def test_caller_connection_survives_file_reading_failure(connection, tmp_path):
    with (
        pytest.raises(duckdb.IOException),
        _materialize_source(tmp_path / "missing.parquet", connection=connection),
    ):
        pytest.fail("A missing source must raise.")

    assert connection.sql("SELECT 1").fetchall() == [(1,)]
