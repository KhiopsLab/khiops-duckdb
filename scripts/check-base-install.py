"""Vérifie le package installé sans dépendances de développement."""

from importlib.metadata import version
from pathlib import Path

import duckdb

import khiops_duckdb
from khiops_duckdb import Table, materialize

assert int(version("duckdb").split(".")[0]) == 2
assert Path(khiops_duckdb.__file__).with_name("py.typed").is_file()
with duckdb.connect() as connection:
    source = connection.sql("SELECT '001' id, 2.5 value")
    with materialize(Table(source, key=("id",))) as data:
        assert Path(data.data_table_path).is_file()
        assert data.dictionary_domain.get_dictionary("main_table").key == ["id"]
        assert data.to_sklearn()["main_table"][0].value.tolist() == [2.5]
    assert not Path(data.data_table_path).exists()
