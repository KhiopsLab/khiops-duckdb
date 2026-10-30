"""Fixtures DuckDB locales et déterministes."""

from collections.abc import Iterator

import duckdb
import pytest


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect(config={"threads": 2}) as connection:
        yield connection


@pytest.fixture
def training_relation(connection: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    return connection.sql(
        """
        SELECT i::VARCHAR AS id, (i % 2)::DOUBLE AS signal,
               CASE WHEN i % 2 = 0 THEN 'no' ELSE 'yes' END AS target
        FROM range(80) AS source(i)
        """
    )
