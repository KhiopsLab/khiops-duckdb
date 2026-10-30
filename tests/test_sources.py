"""Sources fichiers et bases locales réelles."""

import sqlite3

import duckdb
import pytest

from khiops_duckdb import materialize


@pytest.mark.parametrize("format", ["csv", "json", "parquet"])
def test_file_sources(connection, tmp_path, format):
    path = tmp_path / f"source.{format}"
    relation = connection.sql("SELECT * FROM (VALUES (1, 'a'), (2, 'b')) source(n, s)")
    if format == "csv":
        relation.write_csv(str(path), header=True)
        source = connection.read_csv(str(path))
    elif format == "json":
        path.write_text('[{"n":1,"s":"a"},{"n":2,"s":"b"}]')
        source = connection.read_json(str(path))
    else:
        relation.write_parquet(str(path))
        source = connection.read_parquet(str(path))
    with materialize(source.filter("n > 1")) as data:
        frame = data.to_sklearn()["main_table"][0]
        assert frame.n.tolist() == [2.0]
        assert frame.s.tolist() == ["b"]


def test_attached_duckdb_database(connection, tmp_path):
    path = tmp_path / "source.duckdb"
    with duckdb.connect(str(path)) as database:
        database.execute("CREATE TABLE observations AS SELECT 3 n")
    connection.execute(f"ATTACH '{path}' AS upstream (READ_ONLY)")
    with materialize(connection.table("upstream.observations")) as data:
        assert data.to_sklearn()["main_table"][0].n.tolist() == [3.0]


@pytest.mark.integration
def test_sqlite_database_extension(connection, tmp_path):
    path = tmp_path / "source.sqlite"
    with sqlite3.connect(path) as database:
        database.execute("CREATE TABLE observations (id TEXT, value REAL)")
        database.executemany(
            "INSERT INTO observations VALUES (?, ?)", [("001", 2.5), ("002", 3.5)]
        )
    connection.load_extension("sqlite")
    relation = connection.sql(
        "SELECT * FROM sqlite_scan(?, 'observations')", params=[str(path)]
    )
    with materialize(relation.filter("value > 3")) as data:
        assert data.to_sklearn()["main_table"][0].id.tolist() == ["002"]


def test_globbed_partitioned_parquet(connection, tmp_path):
    for i in range(2):
        connection.sql("SELECT ? n", params=[i]).write_parquet(
            str(tmp_path / f"{i}.parquet")
        )
    source = connection.read_parquet(str(tmp_path / "*.parquet"))
    with materialize(source.order("n")) as data:
        assert data.to_sklearn()["main_table"][0].n.tolist() == [0.0, 1.0]
