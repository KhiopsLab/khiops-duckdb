"""API de haut niveau, délégation native et durée de vie des fichiers."""

import inspect
from contextlib import nullcontext
from copy import deepcopy
from functools import wraps
from pathlib import Path

import khiops.core as kh
import pytest

import khiops_duckdb
from khiops_duckdb import Source, Table, core, materialize

_OPTIONS = {
    "build_dictionary_from_data_table": {},
    "check_database": {},
    "deploy_coclustering": {
        "coclustering_file_path": "coclustering.khcj",
        "key_variable_names": ["id"],
        "deployed_variable_name": "id",
    },
    "deploy_model": {"model": "model.kdic", "dictionary_name": "SNB_main_table"},
    "deploy_predictor_for_metrics": {
        "model": "model.kdic",
        "dictionary_name": "SNB_main_table",
    },
    "detect_data_table_format": {},
    "evaluate_predictor": {"model": "model.kdic", "dictionary_name": "SNB_main_table"},
    "extract_keys_from_data_table": {},
    "sort_data_table": {},
    "train_coclustering": {"coclustering_variables": ["id", "signal"]},
    "train_instance_variable_coclustering": {},
    "train_predictor": {"target": "target"},
    "train_recoder": {"target": "target"},
}


def test_every_public_table_consuming_core_function_is_adapted():
    expected = {
        name
        for name, function in inspect.getmembers(kh, inspect.isfunction)
        if not name.startswith("_")
        and "data_table_path" in inspect.signature(function).parameters
    }

    assert set(core.__all__) == expected == set(_OPTIONS)
    for name in expected:
        assert getattr(khiops_duckdb, name) is getattr(core, name)
        assert inspect.signature(getattr(core, name)).parameters["source"]


@pytest.mark.parametrize("name", _OPTIONS)
def test_each_adapter_passes_snapshot_arguments_and_retains_outputs(
    name, training_relation, monkeypatch, tmp_path
):
    calls = []
    original = getattr(kh, name)
    parameters = inspect.signature(original).parameters

    @wraps(original)
    def native(**kwargs):
        snapshot = Path(kwargs["data_table_path"])
        assert snapshot.is_file()
        assert len(snapshot.read_text().splitlines()) == 81
        if "header_line" in parameters:
            assert kwargs["header_line"] is True
            assert kwargs["field_separator"] == "\t"
            assert kwargs["detect_format"] is False
        if "additional_data_tables" in parameters:
            assert kwargs["additional_data_tables"] == {}
        for key in core._OUTPUTS.get(name, {}):
            Path(kwargs[key]).write_text("output")
        calls.append(kwargs)
        if name in {"train_predictor", "train_recoder"}:
            model = str(Path(kwargs["analysis_report_file_path"]).with_suffix(".kdic"))
            Path(model).write_text("model")
            return kwargs["analysis_report_file_path"], model
        if name in {"train_coclustering", "train_instance_variable_coclustering"}:
            return kwargs["coclustering_report_file_path"]
        if name == "deploy_coclustering":
            return (
                kwargs["output_data_table_path"],
                kwargs["coclustering_dictionary_file_path"],
            )
        if name == "evaluate_predictor":
            return kwargs["evaluation_report_file_path"]
        if name == "detect_data_table_format":
            return True, "\t"
        return None

    monkeypatch.setattr(kh, name, native)
    result = getattr(core, name)(
        training_relation, output_dir=tmp_path / name, **_OPTIONS[name]
    )

    assert len(calls) == 1
    assert not Path(calls[0]["data_table_path"]).exists()
    if name == "check_database":
        assert result is None
    elif name == "detect_data_table_format":
        assert result == (True, "\t")
    else:
        paths = result if isinstance(result, tuple) else (result,)
        assert all(Path(path).is_file() for path in paths)


def test_native_options_and_explicit_output_paths_are_preserved(
    training_relation, monkeypatch, tmp_path
):
    captured = {}
    original = kh.train_predictor

    @wraps(original)
    def native(**kwargs):
        captured.update(kwargs)
        return kwargs["analysis_report_file_path"], None

    monkeypatch.setattr(kh, "train_predictor", native)
    report = tmp_path / "custom.khj"

    result = core.train_predictor(
        training_relation,
        target_variable="",
        analysis_report_file_path=report,
        output_dir=tmp_path / "unused",
        max_trees=0,
        sample_percentage=42,
        construction_rules=["Count"],
    )

    assert result == (str(report), None)
    assert captured["target_variable"] == ""
    assert captured["max_trees"] == 0
    assert captured["sample_percentage"] == 42
    assert captured["construction_rules"] == ["Count"]
    assert not (tmp_path / "unused").exists()


def test_implicit_output_directories_are_unique_and_persistent(
    training_relation, monkeypatch, tmp_path
):
    original = kh.train_coclustering

    @wraps(original)
    def native(**kwargs):
        path = Path(kwargs["coclustering_report_file_path"])
        path.write_text("report")
        return str(path)

    monkeypatch.setattr(kh, "train_coclustering", native)
    monkeypatch.chdir(tmp_path)
    paths = [
        core.train_coclustering(
            training_relation, coclustering_variables=["signal", "target"]
        )
        for _ in range(2)
    ]

    assert paths[0] != paths[1]
    assert all(Path(path).is_file() for path in paths)
    assert all(Path(path).is_relative_to(tmp_path / "khiops-results") for path in paths)


def test_native_failure_cleans_snapshots_and_preserves_caller_connection(
    connection, training_relation, monkeypatch, tmp_path
):
    paths = []
    original = kh.train_predictor

    @wraps(original)
    def native(**kwargs):
        paths.append(Path(kwargs["data_table_path"]))
        raise RuntimeError("native failure")

    monkeypatch.setattr(kh, "train_predictor", native)
    with pytest.raises(RuntimeError, match="native failure"):
        core.train_predictor(training_relation, target="target", output_dir=tmp_path)

    assert paths and all(not path.exists() for path in paths)
    assert connection.sql("SELECT 1").fetchall() == [(1,)]


@pytest.mark.parametrize("name", _OPTIONS)
@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("managed", [False, True])
def test_all_adapters_reuse_caller_datasets_without_closing_them(
    name, cached, managed, training_relation, monkeypatch, tmp_path
):
    if cached:
        data = materialize(
            training_relation, cache_key="v1", cache_dir=tmp_path / "cache"
        )
    else:
        data = materialize(training_relation)
    original = getattr(kh, name)
    result = object()

    @wraps(original)
    def native(**kwargs):
        assert kwargs["data_table_path"] == data.data_table_path
        return result

    monkeypatch.setattr(kh, name, native)
    with data if managed else nullcontext(data):
        assert (
            getattr(core, name)(data, output_dir=tmp_path / name, **_OPTIONS[name])
            is result
        )
        assert Path(data.data_table_path).is_file()
    assert Path(data.data_table_path).exists() is not managed
    data.close()
    assert not Path(data.data_table_path).exists()


def test_native_failure_does_not_delete_a_caller_materialized_dataset(
    training_relation, monkeypatch, tmp_path
):
    data = materialize(training_relation, cache_key="v1", cache_dir=tmp_path)
    original = kh.train_predictor

    @wraps(original)
    def native(**kwargs):
        raise RuntimeError("native failure")

    monkeypatch.setattr(kh, "train_predictor", native)
    with pytest.raises(RuntimeError, match="native failure"):
        core.train_predictor(data, target="target", output_dir=tmp_path / "job")
    assert Path(data.data_table_path).is_file()


@pytest.mark.parametrize("option", ["connection", "additional_tables"])
def test_caller_datasets_reject_extra_table_arguments(
    option, training_relation, connection, tmp_path
):
    with materialize(training_relation) as data:
        extra = connection if option == "connection" else {"child": training_relation}
        with pytest.raises(ValueError, match="already contains"):
            core.train_predictor(
                data, target="target", output_dir=tmp_path, **{option: extra}
            )


@pytest.mark.integration
def test_materialized_dataset_supports_custom_kdic_and_keeps_model_outputs(
    training_relation, tmp_path
):
    data = materialize(training_relation, cache_key="v1", cache_dir=tmp_path / "cache")
    schema = Path(data.dictionary_file_path).read_bytes()
    custom = kh.DictionaryDomain()
    dictionary = kh.Dictionary()
    dictionary.name = "Customers"
    for variable in data.dictionary_domain.get_dictionary("main_table").variables:
        dictionary.add_variable(deepcopy(variable))
    custom.add_dictionary(dictionary)
    custom_path = tmp_path / "custom.kdic"
    custom.export_khiops_dictionary_file(str(custom_path))
    custom_contents = custom_path.read_bytes()

    report, model = core.train_predictor(
        data,
        target="target",
        dictionary_file_path_or_domain=str(custom_path),
        dictionary_name="Customers",
        output_dir=tmp_path / "train",
        max_cores=1,
    )
    predictions = core.deploy_model(
        data, model=model, output_dir=tmp_path / "predict", max_cores=1
    )

    assert all(Path(path).is_file() for path in (report, model, predictions))
    assert Path(data.dictionary_file_path).read_bytes() == schema
    assert Path(data.data_table_path).is_file()
    assert custom_path.read_bytes() == custom_contents
    assert len(data.to_sklearn()["main_table"][0]) == 80


def test_source_relation_is_executed_only_once(connection, monkeypatch, tmp_path):
    observed = []

    def observe(value):
        observed.append(value)
        return str(value)

    connection.create_function(
        "observe", observe, ["BIGINT"], "VARCHAR", side_effects=True
    )
    source = connection.sql(
        "SELECT observe(i) id, (i % 2)::VARCHAR target FROM range(80) t(i)"
    )
    original = kh.train_predictor

    @wraps(original)
    def native(**kwargs):
        assert Path(kwargs["data_table_path"]).is_file()
        return kwargs["analysis_report_file_path"], None

    monkeypatch.setattr(kh, "train_predictor", native)
    core.train_predictor(source, target="target", output_dir=tmp_path)

    assert observed == list(range(80))


@pytest.mark.parametrize(
    ("name", "options", "match"),
    [
        ("train_predictor", {}, "Specify target"),
        ("train_predictor", {"target": "a", "target_variable": "b"}, "not both"),
        ("train_predictor", {"field_separator": ","}, "managed automatically"),
        ("train_predictor", {"data_table_path": "x"}, "managed automatically"),
        ("train_predictor", {"additional_data_tables": {}}, "managed automatically"),
        ("check_database", {"target": "a"}, "does not accept target"),
        ("deploy_model", {}, "requires model"),
        ("evaluate_predictor", {}, "requires model"),
        ("deploy_model", {"model": "a", "dictionary_file_path_or_domain": "b"}, "both"),
        (
            "evaluate_predictor",
            {"model": "a", "dictionary_name": "b", "train_dictionary_name": "c"},
            "not both",
        ),
    ],
)
def test_invalid_options_raise_before_reading_sources(name, options, match):
    with pytest.raises(TypeError, match=match):
        getattr(core, name)("does-not-exist.parquet", **options)


@pytest.mark.parametrize(
    "name",
    [
        "build_dictionary_from_data_table",
        "deploy_coclustering",
        "detect_data_table_format",
        "extract_keys_from_data_table",
        "sort_data_table",
    ],
)
def test_single_table_tasks_reject_secondary_tables(name, training_relation):
    with pytest.raises(TypeError, match="does not support additional tables"):
        getattr(core, name)(
            training_relation, additional_tables={"orders": training_relation}
        )


def test_model_dictionary_selection_is_explicit_when_ambiguous():
    domain = kh.DictionaryDomain()
    for name in ("first", "second"):
        dictionary = kh.Dictionary()
        dictionary.name = name
        domain.add_dictionary(dictionary)

    with pytest.raises(ValueError, match="unique model dictionary"):
        core._model_dictionary_name(domain)
    with pytest.raises(TypeError, match="model must be"):
        core._model_dictionary_name(42)


def test_model_dictionary_selection_prefers_the_unique_root():
    domain = kh.DictionaryDomain()
    for name in ("child", "parent"):
        dictionary = kh.Dictionary()
        dictionary.name = name
        dictionary.root = name == "parent"
        domain.add_dictionary(dictionary)

    assert core._model_dictionary_name(domain) == "parent"


def test_source_free_apis_are_native_and_private_names_are_not_proxied():
    assert core.read_dictionary_file is kh.read_dictionary_file
    assert core.simplify_coclustering is kh.simplify_coclustering
    assert core.DictionaryDomain is kh.DictionaryDomain
    with pytest.raises(AttributeError):
        assert core._missing


@pytest.mark.integration
def test_high_level_file_training_deployment_evaluation_and_recoding(
    training_relation, tmp_path
):
    source = tmp_path / "train.parquet"
    training_relation.write_parquet(str(source))
    report, model = core.train_predictor(
        source,
        target="target",
        output_dir=tmp_path / "train",
        max_trees=0,
        max_cores=1,
        sample_percentage=100,
        use_complement_as_test=False,
    )
    predictions = core.deploy_model(
        source, model=Path(model), output_dir=tmp_path / "deploy", max_cores=1
    )
    evaluation = core.evaluate_predictor(
        source, model=model, output_dir=tmp_path / "evaluate", max_cores=1
    )
    metrics = core.deploy_predictor_for_metrics(
        source, model=model, output_dir=tmp_path / "metrics"
    )
    recoder_report, recoder = core.train_recoder(
        source,
        target="target",
        output_dir=tmp_path / "recoder",
        max_trees=0,
        max_cores=1,
    )
    recoded = core.deploy_model(
        source, model=recoder, output_dir=tmp_path / "recode", max_cores=1
    )

    assert all(
        Path(path).is_file()
        for path in (
            report,
            model,
            predictions,
            evaluation,
            metrics,
            recoder_report,
            recoder,
            recoded,
        )
    )
    assert len(Path(predictions).read_text().splitlines()) == 81
    assert core.detect_data_table_format(source, max_cores=1) == (True, "\t")


@pytest.mark.integration
def test_high_level_multitable_training_accepts_file_sources(
    connection, training_relation, tmp_path
):
    source = tmp_path / "customers.parquet"
    orders = tmp_path / "orders.parquet"
    training_relation.write_parquet(str(source))
    connection.sql(
        "SELECT (i // 2)::VARCHAR id, i::VARCHAR order_id FROM range(160) t(i)"
    ).write_parquet(str(orders))

    report, model = core.train_predictor(
        Source(source, key=("id",)),
        additional_tables={"orders": Source(orders, key=("id", "order_id"))},
        target="target",
        output_dir=tmp_path / "model",
        max_trees=0,
        max_cores=1,
        sample_percentage=100,
        use_complement_as_test=False,
    )

    assert Path(report).is_file() and Path(model).is_file()
    predictions = core.deploy_model(
        Source(source, key=("id",)),
        additional_tables={"orders": Source(orders, key=("id", "order_id"))},
        model=model,
        output_dir=tmp_path / "predict",
        max_cores=1,
    )
    evaluation = core.evaluate_predictor(
        Source(source, key=("id",)),
        additional_tables={"orders": Source(orders, key=("id", "order_id"))},
        model=model,
        output_dir=tmp_path / "evaluate",
        max_cores=1,
    )
    assert Path(evaluation).is_file()
    assert len(Path(predictions).read_text().splitlines()) == 81


@pytest.mark.integration
def test_high_level_database_relation_and_table_utilities(connection, tmp_path):
    database = tmp_path / "warehouse.duckdb"
    connection.execute(f"ATTACH '{database}' AS warehouse")
    connection.execute(
        "CREATE TABLE warehouse.customers AS "
        "SELECT i::VARCHAR id, i % 2 signal FROM range(80) t(i)"
    )
    source = Table(connection.table("warehouse.customers"), key=("id",))

    core.check_database(source, max_cores=1)
    dictionary = core.build_dictionary_from_data_table(
        source, output_dir=tmp_path / "dictionary", max_cores=1
    )
    sorted_path = core.sort_data_table(
        source, sort_variables=["id"], output_dir=tmp_path / "sort", max_cores=1
    )
    keys = core.extract_keys_from_data_table(
        source, output_dir=tmp_path / "keys", max_cores=1
    )

    assert all(Path(path).is_file() for path in (dictionary, sorted_path, keys))
    assert Path(keys).read_text().splitlines()[0] == "id"
    assert connection.sql("SELECT count(*) FROM warehouse.customers").fetchall() == [
        (80,)
    ]


@pytest.mark.integration
def test_high_level_coclustering_training_and_deployment(connection, tmp_path):
    source = connection.sql(
        """
        SELECT 'id' || (i // 10)::VARCHAR id,
               'segment' || ((i // 10) % 2)::VARCHAR segment
        FROM range(800) t(i)
        """
    ).order("id")

    report = core.train_coclustering(
        source,
        coclustering_variables=["id", "segment"],
        output_dir=tmp_path / "train",
        max_cores=1,
    )
    predictions, model = core.deploy_coclustering(
        source,
        coclustering_file_path=report,
        key_variable_names=["id"],
        deployed_variable_name="id",
        output_dir=tmp_path / "deploy",
    )

    assert all(Path(path).is_file() for path in (report, predictions, model))


@pytest.mark.integration
def test_high_level_instance_variable_coclustering(connection, tmp_path):
    source = connection.sql(
        "SELECT (i % 2)::DOUBLE a, (i % 2)::DOUBLE b, (i % 2)::DOUBLE c "
        "FROM range(100) t(i)"
    )

    report = core.train_instance_variable_coclustering(
        source, output_dir=tmp_path, max_cores=1
    )

    assert Path(report).is_file()
