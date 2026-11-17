"""Local, deterministic DuckDB fixtures."""

from collections.abc import Iterator

import duckdb
import pytest


@pytest.fixture
def connection() -> Iterator[duckdb.DuckDBPyConnection]:
    with duckdb.connect(config={"threads": 2}) as connection:
        yield connection
