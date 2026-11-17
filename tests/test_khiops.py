"""Both functions against the real Khiops engine."""

import csv

import khiops.core as kh
import pytest

from khiops_duckdb import build_dictionary_from_relation, export_data_table

pytestmark = pytest.mark.integration


def read_records(path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def test_khiops_trains_and_deploys_from_the_export_and_dictionary(connection, tmp_path):
    customers = connection.sql(
        """
        SELECT i AS id, (i % 2)::DOUBLE AS signal,
               CASE WHEN i % 2 = 0 THEN 'no' ELSE 'yes' END AS churn
        FROM range(80) AS source(i)
        """
    )
    dictionary_domain = build_dictionary_from_relation(
        customers, "Customer", key=["id"]
    )
    data_table_path = export_data_table(
        customers, tmp_path / "customers.tsv", dictionary_domain, "Customer"
    )

    report_file_path, model_dictionary_file_path = kh.train_predictor(
        dictionary_domain,
        "Customer",
        data_table_path,
        "churn",
        str(tmp_path / "report.khj"),
        sample_percentage=100,
        use_complement_as_test=False,
        max_trees=0,
        max_cores=1,
    )
    test_table_path = export_data_table(
        customers.filter("id < 20").project("id, signal, 'unused' AS unknown"),
        tmp_path / "test.tsv",
        model_dictionary_file_path,
        "SNB_Customer",
    )
    kh.deploy_model(
        model_dictionary_file_path,
        "SNB_Customer",
        test_table_path,
        str(tmp_path / "scores.tsv"),
        max_cores=1,
    )

    scores = read_records(tmp_path / "scores.tsv")
    assert (tmp_path / "report.khj").is_file()
    assert (tmp_path / "test.tsv").read_text().splitlines()[0] == "id\tsignal"
    assert [row["id"] for row in scores] == sorted(str(i) for i in range(20))
    assert all(
        row["Predictedchurn"] == ("no" if int(row["id"]) % 2 == 0 else "yes")
        for row in scores
    )


def test_khiops_joins_exports_of_nested_tables_and_entities(connection, tmp_path):
    relations = {
        "Customer": connection.sql("SELECT i AS id FROM range(1, 13) t(i)"),
        "Order": connection.sql(
            "SELECT c AS id, o AS order_id FROM range(1, 13) a(c), range(12) b(o) "
            "WHERE o < c"
        ),
        "Line": connection.sql(
            "SELECT c AS id, o AS order_id, l AS line_id "
            "FROM range(1, 13) a(c), range(12) b(o), range(2) d(l) WHERE o < c"
        ),
        "Address": connection.sql(
            "SELECT i AS id, 'city' || i AS city FROM range(1, 13) t(i)"
        ),
    }
    dictionary_domain = build_dictionary_from_relation(
        relations["Customer"], "Customer", key=["id"]
    )
    build_dictionary_from_relation(
        relations["Order"],
        "Order",
        key=["id", "order_id"],
        dictionary_domain=dictionary_domain,
        parent_dictionary_name="Customer",
    )
    build_dictionary_from_relation(
        relations["Line"],
        "Line",
        key=["id", "order_id", "line_id"],
        dictionary_domain=dictionary_domain,
        parent_dictionary_name="Order",
    )
    build_dictionary_from_relation(
        relations["Address"],
        "Address",
        key=["id"],
        dictionary_domain=dictionary_domain,
        parent_dictionary_name="Customer",
        entity=True,
    )
    customer = dictionary_domain.get_dictionary("Customer")
    customer.add_variable_from_spec(
        name="line_count", type="Numerical", rule="TableSum(Order, TableCount(Line))"
    )
    customer.add_variable_from_spec(
        name="city", type="Categorical", rule="GetValueC(Address, city)"
    )
    paths = {
        name: export_data_table(
            relation, tmp_path / f"{name}.tsv", dictionary_domain, name
        )
        for name, relation in relations.items()
    }

    kh.deploy_model(
        dictionary_domain,
        "Customer",
        paths["Customer"],
        str(tmp_path / "features.tsv"),
        additional_data_tables={
            "Order": paths["Order"],
            "Order/Line": paths["Line"],
            "Address": paths["Address"],
        },
        max_cores=1,
    )

    features = read_records(tmp_path / "features.tsv")
    assert [row["id"] for row in features] == sorted(str(i) for i in range(1, 13))
    assert all(
        row
        == {
            "id": row["id"],
            "line_count": str(2 * int(row["id"])),
            "city": f"city{row['id']}",
        }
        for row in features
    )


def test_khiops_parses_exported_temporal_and_text_values(connection, tmp_path):
    relation = connection.sql(
        """SELECT DATE '2026-01-02' d, TIME '12:34:56.123' t,
           TIMESTAMP '2026-01-02 12:34:56.123' ts, 'a\t"b"' text, 'x\ny' note,
           NULL::DOUBLE amount"""
    )
    dictionary_domain = build_dictionary_from_relation(relation, "Event")
    data_table_path = export_data_table(relation, tmp_path / "events.tsv")

    kh.deploy_model(
        dictionary_domain,
        "Event",
        data_table_path,
        str(tmp_path / "copy.tsv"),
        max_cores=1,
    )

    assert read_records(tmp_path / "copy.tsv") == [
        {
            "d": "2026-01-02",
            "t": "12:34:56.123",
            "ts": "2026-01-02 12:34:56.123",
            "text": 'a\t"b"',
            "note": "x y",
            "amount": "",
        }
    ]


DATE_FORMATS = [
    *("YYYY-MM-DD", "YYYY/MM/DD", "YYYY.MM.DD", "YYYYMMDD"),
    *("DD-MM-YYYY", "DD/MM/YYYY", "DD.MM.YYYY", "DDMMYYYY"),
    *("YYYY-DD-MM", "YYYY/DD/MM", "YYYY.DD.MM", "YYYYDDMM"),
    *("MM-DD-YYYY", "MM/DD/YYYY", "MM.DD.YYYY", "MMDDYYYY"),
]
TIME_FORMATS = [
    *("HH:MM:SS", "HH:MM:SS.", "HH:MM"),
    *("HH.MM.SS", "HH.MM.SS.", "HH.MM"),
    *("(H)H:(M)M:(S)S", "(H)H:(M)M:(S)S.", "(H)H:(M)M"),
    *("(H)H.(M)M.(S)S", "(H)H.(M)M.(S)S.", "(H)H.(M)M"),
    *("HHMMSS", "HHMMSS.", "HHMM"),
]
CANONICAL = {
    "Date": 'FormatDate({}, "YYYY-MM-DD")',
    "Time": 'FormatTime({}, "HH:MM:SS.")',
    "Timestamp": 'FormatTimestamp({}, "YYYY-MM-DD HH:MM:SS.")',
    "TimestampTZ": 'FormatTimestamp(UtcTimestamp({}), "YYYY-MM-DD HH:MM:SS.")',
}


def time_kept_by(time_format: str, time: str) -> str:
    if time_format.endswith("."):
        return time
    return time[:8] if "S" in time_format else f"{time[:5]}:00"


def documented_formats(
    date: str, time: str, utc_time: str
) -> list[tuple[str, str, str, str]]:
    """Type, format, DuckDB value and the value Khiops should read back."""
    compact_dates = [text for text in DATE_FORMATS if text.isalpha()]
    timestamps = [
        (date_format + separator + time_format, time_format)
        for date_format in DATE_FORMATS
        for separator in " -_T"
        for time_format in TIME_FORMATS
    ] + [
        (date_format + time_format, time_format)
        for date_format in compact_dates
        for time_format in ("HHMMSS", "HHMMSS.", "HHMM")
    ]
    return (
        [("Date", text, f"DATE '{date}'", date) for text in DATE_FORMATS]
        + [
            ("Time", text, f"TIME '{time}'", time_kept_by(text, time))
            for text in TIME_FORMATS
        ]
        + [
            (
                "Timestamp",
                text,
                f"TIMESTAMP '{date} {time}'",
                f"{date} {time_kept_by(time_format, time)}",
            )
            for text, time_format in timestamps
        ]
        + [
            (
                "TimestampTZ",
                text + zone,
                f"TIMESTAMPTZ '{date} {time}+01'",
                f"{date} {time_kept_by(time_format, utc_time)}",
            )
            for text, time_format in timestamps[:: len(timestamps) // 20]
            for zone in ("zzzzz", "zzzzzz")
        ]
    )


@pytest.mark.parametrize(
    "date,time,utc_time",
    [
        ("2026-03-04", "05:06:07.089", "04:06:07.089"),
        ("1999-12-31", "23:59:58.007", "22:59:58.007"),
    ],
)
def test_khiops_reads_back_every_date_and_time_format_it_documents(
    connection, tmp_path, date, time, utc_time
):
    formats = documented_formats(date, time, utc_time)
    relation = connection.sql(
        "SELECT "
        + ", ".join(f"{value} AS v{i}" for i, (_, _, value, _) in enumerate(formats))
    )
    dictionary = kh.Dictionary()
    dictionary.name = "Event"
    for i, (kind, khiops_format, _, _) in enumerate(formats):
        dictionary.add_variable_from_spec(
            name=f"v{i}",
            type=kind,
            used=False,
            meta_data={f"{kind}Format": khiops_format},
        )
        dictionary.add_variable_from_spec(
            name=f"read{i}", type="Categorical", rule=CANONICAL[kind].format(f"v{i}")
        )
    dictionary_domain = kh.DictionaryDomain()
    dictionary_domain.add_dictionary(dictionary)
    data_table_path = export_data_table(
        relation, tmp_path / "events.tsv", dictionary_domain, "Event"
    )

    kh.deploy_model(
        dictionary_domain,
        "Event",
        data_table_path,
        str(tmp_path / "read.tsv"),
        max_cores=1,
    )

    (record,) = read_records(tmp_path / "read.tsv")
    misread = {
        (kind, khiops_format): record[f"read{i}"]
        for i, (kind, khiops_format, _, expected) in enumerate(formats)
        if record[f"read{i}"] != expected
    }
    assert len(formats) > 1000
    assert misread == {}
