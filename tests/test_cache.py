"""Réutilisation des instantanés et reprise après interruption."""

import json
import multiprocessing
from contextlib import nullcontext
from pathlib import Path

import duckdb
import pytest

from khiops_duckdb import Source, materialize, remove_dataset


def _concurrent_prepare(cache_dir, observed, pipe):
    with duckdb.connect(config={"threads": 2}) as connection:

        def observe(value):
            with open(observed, "ab") as stream:
                stream.write(b"x")
            return value

        connection.create_function(
            "observe", observe, ["BIGINT"], "BIGINT", side_effects=True
        )
        source = connection.sql("SELECT observe(i) value FROM range(80) t(i)")
        data = materialize(source, cache_dir=cache_dir, cache_key="shared")
        pipe.send(data.data_table_path)
        pipe.close()


def _interrupted_prepare(cache_dir, pipe):
    with duckdb.connect(config={"threads": 2}) as connection:

        def pause(value):
            pipe.send("exporting")
            pipe.recv()
            return value

        connection.create_function(
            "pause", pause, ["INTEGER"], "INTEGER", side_effects=True
        )
        materialize(
            connection.sql("SELECT pause(1) value"),
            cache_dir=cache_dir,
            cache_key="interrupted",
        )


def _retained_materialization(cache_dir, cache_key, pipe):
    with duckdb.connect(config={"threads": 2}) as connection:
        data = materialize(
            connection.sql("SELECT 1 value"),
            cache_dir=cache_dir,
            cache_key=cache_key,
        )
        pipe.send((data.data_table_path, data.dictionary_file_path))
        pipe.close()


def test_plain_materialization_retains_tsv_and_input_dictionary(connection, tmp_path):
    data = materialize(
        connection.sql("SELECT 'a' category, 1 value"),
        cache_key="v1",
        cache_dir=tmp_path,
    )

    assert Path(data.data_table_path).is_file()
    assert Path(data.dictionary_file_path).is_file()
    assert data.dictionary_name == "main_table"
    assert data.to_sklearn()["main_table"][0].value.tolist() == [1]


@pytest.mark.parametrize("cache_key", [None, "v1"])
@pytest.mark.parametrize("fails", [False, True])
def test_context_exit_removes_the_snapshot_regardless_of_cache_key(
    connection, tmp_path, cache_key, fails
):
    expected = pytest.raises(RuntimeError, match="caller") if fails else nullcontext()
    with expected:
        with materialize(
            connection.sql("SELECT 1 value"), cache_key=cache_key, cache_dir=tmp_path
        ) as data:
            assert Path(data.dictionary_file_path).is_file()
            if fails:
                raise RuntimeError("caller")

    data.close()
    assert not data.directory.exists()


def test_context_exit_also_removes_a_reopened_version(connection, tmp_path):
    original = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    with materialize(cache_key="v1", cache_dir=tmp_path) as reopened:
        assert reopened.data_table_path == original.data_table_path

    assert not original.directory.exists()
    with pytest.raises(FileNotFoundError, match="No materialized dataset"):
        materialize(cache_key="v1", cache_dir=tmp_path)


def test_close_is_idempotent_and_does_not_remove_a_subsequent_export(
    connection, tmp_path
):
    first = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    first.close()
    second = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )

    first.close()

    assert second.to_sklearn()["main_table"][0].value.tolist() == [1]


@pytest.mark.parametrize("cache_key", [None, "v1"])
def test_plain_materialization_survives_normal_process_exit(tmp_path, cache_key):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_retained_materialization,
        args=(str(tmp_path), cache_key, child),
    )
    process.start()
    child.close()
    try:
        assert parent.poll(30), "Materialization worker did not report its paths."
        paths = parent.recv()
        process.join(30)
        assert process.exitcode == 0
        assert all(Path(path).is_file() for path in paths)
    finally:
        if process.is_alive():
            process.kill()
            process.join(10)
        parent.close()


def test_cache_hit_does_not_execute_the_source_again(connection, tmp_path):
    connection.execute("CREATE SEQUENCE sequence")
    source = connection.sql("SELECT nextval('sequence') value")
    first = materialize(source, cache_key="v1", cache_dir=tmp_path)
    second = materialize(source, cache_key="v1", cache_dir=tmp_path)
    reopened = materialize(cache_key="v1", cache_dir=tmp_path)

    assert first.data_table_path == second.data_table_path == reopened.data_table_path
    assert reopened.to_sklearn()["main_table"][0].value.tolist() == [1]
    assert connection.sql("SELECT currval('sequence')").fetchall() == [(1,)]


def test_new_version_refreshes_data_without_changing_the_previous_snapshot(
    connection, tmp_path
):
    first = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    second = materialize(
        connection.sql("SELECT 2 value"), cache_key="v2", cache_dir=tmp_path
    )

    assert first.directory != second.directory
    assert first.to_sklearn()["main_table"][0].value.tolist() == [1]
    assert second.to_sklearn()["main_table"][0].value.tolist() == [2]


def test_prepared_files_are_portable_and_keep_multitable_metadata(connection, tmp_path):
    source = tmp_path / "customers.parquet"
    connection.sql("SELECT 'c1' id, 42 age").write_parquet(str(source))
    profile = Source(
        connection.sql("SELECT 'c1' id, 'hello' body"),
        key=("id",),
        types={"body": "Text"},
        entity=True,
    )
    data = materialize(
        Source(source, key=("id",)),
        additional_tables={"profile": profile},
        cache_key="v1",
        cache_dir=tmp_path / "cache",
        connection=connection,
    )
    source.unlink()
    assert connection.sql("SELECT 1").fetchall() == [(1,)]
    moved = tmp_path / "moved"
    (tmp_path / "cache").rename(moved)

    reopened = materialize(cache_key="v1", cache_dir=moved)

    assert reopened.dictionary_domain.get_dictionary("main_table").root
    assert (
        reopened.dictionary_domain.get_dictionary("profile").get_variable("body").type
        == "Text"
    )
    assert reopened.to_sklearn()["additional_data_tables"]["profile"][2] is True
    assert Path(reopened.data_table_path).is_relative_to(moved)
    assert data.directory.name == reopened.directory.name


def test_failed_preparation_is_not_published_and_can_be_retried(connection, tmp_path):
    with pytest.raises(ValueError, match="NaN or infinity"):
        materialize(
            connection.sql("SELECT 'nan'::DOUBLE value"),
            cache_key="v1",
            cache_dir=tmp_path,
        )
    assert not any(path.is_dir() for path in tmp_path.iterdir())
    with pytest.raises(FileNotFoundError, match="No materialized dataset"):
        materialize(cache_key="v1", cache_dir=tmp_path)

    data = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    assert data.to_sklearn()["main_table"][0].value.tolist() == [1]


@pytest.mark.parametrize(
    "key,error", [("", ValueError), ("  ", ValueError), (42, TypeError)]
)
def test_cache_keys_are_explicit_and_nonempty(tmp_path, key, error):
    with pytest.raises(error, match="cache_key"):
        materialize(cache_key=key, cache_dir=tmp_path)


def test_reopening_does_not_silently_ignore_extra_sources(connection, tmp_path):
    with pytest.raises(ValueError, match="Reopening"):
        materialize(cache_key="v1", cache_dir=tmp_path, connection=connection)


def test_default_cache_directory_is_local_and_keys_cannot_escape_it(
    connection, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    data = materialize(connection.sql("SELECT 1 value"), cache_key="../outside")
    assert data.directory.parent == tmp_path / ".khiops-cache"
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize(
    "change",
    ["version", "key", "filename", "types", "size", "keys", "entity", "missing-main"],
)
def test_invalid_cache_metadata_is_not_silently_rebuilt(connection, tmp_path, change):
    data = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    manifest_path = data.directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if change == "version":
        manifest["format_version"] = 100
    elif change == "key":
        manifest["cache_key"] = "different"
    elif change == "filename":
        manifest["tables"][0]["filename"] = "../foreign.tsv"
    elif change == "types":
        manifest["tables"][0]["types"] = {"value": "Unknown"}
    elif change == "size":
        manifest["tables"][0]["size"] += 1
    elif change == "keys":
        manifest["tables"][0]["key"] = ["missing"]
    elif change == "entity":
        manifest["tables"][0]["entity"] = "yes"
    else:
        manifest["tables"][0]["path"] = "child"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="dataset"):
        materialize(
            connection.sql("SELECT 2 value"), cache_key="v1", cache_dir=tmp_path
        )


def test_changed_cached_files_are_reported(connection, tmp_path):
    data = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    Path(data.data_table_path).write_text("truncated")

    with pytest.raises(ValueError, match="missing or changed"):
        materialize(cache_key="v1", cache_dir=tmp_path)


def test_explicit_removal_preserves_other_versions_and_parent_files(
    connection, tmp_path
):
    first = materialize(
        connection.sql("SELECT 1 value"), cache_key="v1", cache_dir=tmp_path
    )
    second = materialize(
        connection.sql("SELECT 2 value"), cache_key="v2", cache_dir=tmp_path
    )
    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("keep")

    remove_dataset(cache_key="v1", cache_dir=tmp_path)

    assert not first.directory.exists()
    assert second.to_sklearn()["main_table"][0].value.tolist() == [2]
    assert sentinel.read_text() == "keep"
    with pytest.raises(FileNotFoundError, match="No materialized dataset"):
        remove_dataset(cache_key="v1", cache_dir=tmp_path)


def test_removing_a_missing_cache_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="No cache directory"):
        remove_dataset(cache_key="v1", cache_dir=tmp_path / "absent")


def test_concurrent_processes_export_only_once(tmp_path):
    context = multiprocessing.get_context("spawn")
    cache_dir = tmp_path / "cache"
    observed = tmp_path / "observed"
    workers = []
    try:
        for _ in range(2):
            parent, child = context.Pipe()
            process = context.Process(
                target=_concurrent_prepare,
                args=(str(cache_dir), str(observed), child),
            )
            process.start()
            child.close()
            workers.append((process, parent))
        paths = []
        for process, pipe in workers:
            assert pipe.poll(30), "Materialized dataset worker did not report a result."
            paths.append(pipe.recv())
            process.join(30)
            assert process.exitcode == 0
        assert paths[0] == paths[1]
        assert observed.read_bytes() == b"x" * 80
    finally:
        for process, pipe in workers:
            if process.is_alive():
                process.kill()
                process.join(10)
            pipe.close()


def test_hard_stopped_export_is_recovered_on_next_preparation(connection, tmp_path):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_interrupted_prepare, args=(str(tmp_path), child))
    process.start()
    child.close()
    try:
        assert parent.poll(30), "Export worker did not reach the interruption point."
        assert parent.recv() == "exporting"
        assert list(tmp_path.glob(".*.staging-*"))
    finally:
        if process.is_alive():
            process.kill()
        process.join(10)
        parent.close()
    assert not process.is_alive()

    data = materialize(
        connection.sql("SELECT 2 value"), cache_key="interrupted", cache_dir=tmp_path
    )

    assert data.to_sklearn()["main_table"][0].value.tolist() == [2]
    assert not list(tmp_path.glob(".*.staging-*"))
