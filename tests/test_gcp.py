"""BigQuery results as DuckDB relations, without calling BigQuery."""

import sys

import duckdb
import pyarrow as pa
import pytest

from khiops_duckdb import export_data_table, read_bigquery


class FakeJob:
    def __init__(self, table: pa.Table) -> None:
        self.table = table

    def result(self) -> "FakeJob":
        return self

    def to_arrow_iterable(self, bqstorage_client: object) -> object:
        return iter(self.table.to_batches(max_chunksize=2))

    def to_arrow(self) -> pa.Table:
        return self.table


@pytest.fixture
def bigquery(monkeypatch):
    """Record the calls to a fake BigQuery client that returns ``calls["table"]``."""
    calls = {}

    class FakeClient:
        def __init__(self, project: str | None = None) -> None:
            calls["project"] = project

        def query(self, query: str) -> FakeJob:
            calls["query"] = query
            return FakeJob(calls["table"])

    monkeypatch.setattr("google.cloud.bigquery.Client", FakeClient)
    monkeypatch.setattr("google.cloud.bigquery_storage.BigQueryReadClient", object)
    return calls


def test_query_result_is_exported_as_a_data_table(bigquery, connection, tmp_path):
    bigquery["table"] = pa.table({"id": [1, 2, 3], "churn": ["no", "yes", None]})

    relation = read_bigquery("SELECT 1", project="my-project", connection=connection)
    path = export_data_table(relation, tmp_path / "table.tsv")

    assert bigquery == bigquery | {"project": "my-project", "query": "SELECT 1"}
    assert (tmp_path / "table.tsv").read_text() == 'id\tchurn\n1\tno\n2\tyes\n3\t""\n'
    assert path == str(tmp_path / "table.tsv")


def test_empty_result_keeps_its_columns(bigquery, connection):
    bigquery["table"] = pa.table({"id": pa.array([], pa.int64()), "churn": []})

    relation = read_bigquery("SELECT 1", connection=connection)

    assert relation.columns == ["id", "churn"]
    assert relation.fetchall() == []


def test_result_uses_the_default_connection_and_reads_once(bigquery):
    bigquery["table"] = pa.table({"id": [1, 2, 3]})

    relation = read_bigquery("SELECT 1")

    assert bigquery["project"] is None
    assert relation.fetchall() == [(1,), (2,), (3,)]
    with pytest.raises(duckdb.Error, match="already been consumed"):
        relation.fetchall()


def test_missing_gcp_extra_is_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyarrow", None)

    with pytest.raises(ImportError, match=r"khiops-duckdb\[gcp\]"):
        read_bigquery("SELECT 1")
