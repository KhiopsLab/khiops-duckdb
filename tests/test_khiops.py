"""Intégration avec les API publiques et le véritable moteur Khiops."""

import csv

import khiops.core as kh
import pytest
from khiops.sklearn import KhiopsClassifier, KhiopsEncoder, KhiopsRegressor

from khiops_duckdb import Table, materialize

pytestmark = pytest.mark.integration


def test_core_training_and_deployment(training_relation, tmp_path):
    with materialize(training_relation) as data:
        report_path = tmp_path / "report.khj"
        _, model_path = kh.train_predictor(
            **data.core_args,
            target_variable="target",
            analysis_report_file_path=str(report_path),
            sample_percentage=100,
            use_complement_as_test=False,
            max_trees=0,
            max_cores=1,
        )
        model = kh.read_dictionary_file(model_path)
        output = tmp_path / "predictions.tsv"
        kh.deploy_model(
            model,
            "SNB_main_table",
            output_data_table_path=str(output),
            **data.table_args,
            max_cores=1,
        )
    assert report_path.is_file()
    assert len(model.dictionaries) >= 1
    with output.open() as stream:
        rows = list(csv.reader(stream, delimiter="\t"))
    assert len(rows) == 81
    assert any("Predicted" in name for name in rows[0])


def test_core_reads_nested_tables_and_entity(connection, tmp_path):
    root = Table(connection.sql("SELECT '001' id"), key=("id",))
    orders = Table(
        connection.sql("SELECT '001' id, 'a' order_id"), key=("id", "order_id")
    )
    items = Table(
        connection.sql("SELECT '001' id, 'a' order_id, i amount FROM range(2) t(i)"),
        key=("id", "order_id"),
    )
    profile = Table(
        connection.sql("SELECT '001' id, 'west' region"), key=("id",), entity=True
    )
    with materialize(
        root,
        additional_tables={"orders/items": items, "orders": orders, "profile": profile},
    ) as data:
        variable = kh.Variable()
        variable.name, variable.type = "item_count", "Numerical"
        variable.rule = "TableSum(orders, TableCount(items))"
        data.dictionary_domain.get_dictionary("main_table").add_variable(variable)
        output = tmp_path / "counts.tsv"
        kh.deploy_model(
            **data.core_args, output_data_table_path=str(output), max_cores=1
        )
    with output.open() as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    assert rows == [{"id": "001", "item_count": "2"}]


def test_core_temporal_and_text_values(connection, tmp_path):
    relation = connection.sql(
        """SELECT DATE '2026-01-02' d, TIME '12:34:56.123' t,
           TIMESTAMP '2026-01-02 12:34:56.123' ts, 'a\t"b"' text"""
    )
    with materialize(relation) as data:
        output = tmp_path / "temporal.tsv"
        kh.deploy_model(
            **data.core_args, output_data_table_path=str(output), max_cores=1
        )
    with output.open() as stream:
        row = next(csv.DictReader(stream, delimiter="\t"))
    assert row == {
        "d": "2026-01-02",
        "t": "12:34:56.123",
        "ts": "2026-01-02 12:34:56.123",
        "text": 'a\t"b"',
    }


def test_sklearn_classifier_train_and_predict(training_relation):
    classifier = KhiopsClassifier(n_trees=0, n_cores=1)
    with materialize(training_relation) as data:
        spec = data.to_sklearn()
    target = spec["main_table"][0].pop("target")
    classifier.fit(spec, target)
    prediction = classifier.predict(spec)
    assert (prediction == target.to_numpy()).mean() > 0.95


def test_sklearn_multitable_classifier(connection, training_relation):
    orders = connection.sql(
        """SELECT 'c' || (i // 2)::VARCHAR id, i::VARCHAR order_id, i % 4 amount
           FROM range(160) source(i)"""
    )
    training_relation = training_relation.project("'c' || id AS id, signal, target")
    with materialize(
        Table(training_relation, key=("id",)),
        additional_tables={"orders": Table(orders, key=("id", "order_id"))},
    ) as data:
        spec = data.to_sklearn()
    target = spec["main_table"][0].pop("target")
    classifier = KhiopsClassifier(n_trees=0, n_cores=1)
    classifier.fit(spec, target)
    assert (classifier.predict(spec) == target.to_numpy()).mean() > 0.95


def test_sklearn_regressor_and_encoder(training_relation):
    with materialize(training_relation.project("signal, signal * 2 AS target")) as data:
        spec = data.to_sklearn()
    target = spec["main_table"][0].pop("target")
    regressor = KhiopsRegressor(n_trees=0, n_cores=1)
    regressor.fit(spec, target)
    assert len(regressor.predict(spec)) == 80
    encoder = KhiopsEncoder(n_trees=0, n_cores=1, categorical_target=False)
    transformed = encoder.fit_transform(spec, target)
    assert transformed.shape[0] == 80
