"""BigQuery query results as DuckDB relations."""

import itertools

import duckdb


def read_bigquery(
    query: str,
    *,
    project: str | None = None,
    connection: duckdb.DuckDBPyConnection | None = None,
) -> duckdb.DuckDBPyRelation:
    """Run a BigQuery query and stream its result as a DuckDB relation.

    Requires ``khiops-duckdb[gcp]``. The stream can be read once: export it
    once, or store it with ``relation.create("name")`` to reuse it.

    Args:
        query: GoogleSQL query.
        project: Project that runs the query. The credentials' one by default.
        connection: DuckDB connection of the relation. The default one if omitted.

    Returns:
        A relation over the streamed result.

    Raises:
        ImportError: The ``gcp`` extra is not installed.
    """
    try:
        import pyarrow as pa
        from google.cloud import bigquery, bigquery_storage
    except ImportError as error:
        raise ImportError(
            'read_bigquery requires the gcp extra: pip install "khiops-duckdb[gcp]".'
        ) from error
    job = bigquery.Client(project=project).query(query)
    batches = job.result().to_arrow_iterable(
        bqstorage_client=bigquery_storage.BigQueryReadClient()
    )
    first = next(batches, None)
    if first is None:
        reader = job.result().to_arrow().to_reader()
    else:
        reader = pa.RecordBatchReader.from_batches(
            first.schema, itertools.chain([first], batches)
        )
    if connection is None:
        connection = duckdb.default_connection()
    return connection.from_arrow(reader)
