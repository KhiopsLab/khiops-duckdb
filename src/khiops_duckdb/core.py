"""API Khiops natives acceptant directement des sources DuckDB ou des fichiers."""

import inspect
from collections.abc import Callable, Mapping
from os import PathLike, fspath
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, Protocol, TypeVar

import duckdb
import khiops.core as kh

from khiops_duckdb.dataset import Dataset
from khiops_duckdb.source import SourceLike, _materialize_source

_Result = TypeVar("_Result", covariant=True)


class _SourceFunction(Protocol[_Result]):
    def __call__(
        self,
        source: SourceLike,
        *,
        additional_tables: Mapping[str, SourceLike] | None = None,
        connection: duckdb.DuckDBPyConnection | None = None,
        output_dir: str | PathLike[str] | None = None,
        **options: Any,
    ) -> _Result: ...


_OUTPUTS = {
    "build_dictionary_from_data_table": {
        "output_dictionary_file_path": "dictionary.kdic",
    },
    "deploy_coclustering": {
        "coclustering_dictionary_file_path": "coclustering.kdic",
        "output_data_table_path": "predictions.tsv",
    },
    "deploy_model": {"output_data_table_path": "predictions.tsv"},
    "deploy_predictor_for_metrics": {"output_data_table_path": "metrics.tsv"},
    "evaluate_predictor": {"evaluation_report_file_path": "evaluation.khj"},
    "extract_keys_from_data_table": {"output_data_table_path": "keys.tsv"},
    "sort_data_table": {"output_data_table_path": "sorted.tsv"},
    "train_coclustering": {"coclustering_report_file_path": "coclustering.khcj"},
    "train_instance_variable_coclustering": {
        "coclustering_report_file_path": "coclustering.khcj",
    },
    "train_predictor": {"analysis_report_file_path": "report.khj"},
    "train_recoder": {"analysis_report_file_path": "report.khj"},
}
_MODEL_TASKS = {"deploy_model", "deploy_predictor_for_metrics", "evaluate_predictor"}
_INPUT_OPTIONS = {
    "data_table_path",
    "additional_data_tables",
    "header_line",
    "field_separator",
    "detect_format",
}


def _adapt(name: str, description: str) -> _SourceFunction[_Result]:
    def run(
        source: SourceLike,
        *,
        additional_tables: Mapping[str, SourceLike] | None = None,
        connection: duckdb.DuckDBPyConnection | None = None,
        output_dir: str | PathLike[str] | None = None,
        **options: Any,
    ) -> _Result:
        result: _Result = _run(
            name, source, additional_tables, connection, output_dir, options
        )
        return result

    run.__name__ = name
    run.__qualname__ = name
    run.__doc__ = (
        f"{description}\n\n"
        "Args:\n"
        "    source: Fichier, URL, relation DuckDB, Source ou Table.\n"
        "    additional_tables: Sources secondaires par chemin Khiops.\n"
        "    connection: Connexion pour les fichiers et leurs accès distants.\n"
        "    output_dir: Répertoire des sorties générées automatiquement.\n"
        "    **options: Options natives, plus target et model selon la tâche.\n\n"
        "Les fichiers d'entrée temporaires sont supprimés après l'appel. "
        "Les sorties restent disponibles. Voir la documentation des workflows "
        "natifs pour les valeurs retournées et les options de chaque tâche."
    )
    return run


def _run(
    name: str,
    source: SourceLike,
    additional_tables: Mapping[str, SourceLike] | None,
    connection: duckdb.DuckDBPyConnection | None,
    output_dir: str | PathLike[str] | None,
    options: dict[str, Any],
) -> Any:
    function: Callable[..., Any] = getattr(kh, name)
    parameters = inspect.signature(function).parameters
    forbidden = _INPUT_OPTIONS.intersection(options)
    if forbidden:
        raise TypeError(
            "Source arguments are managed automatically: "
            f"{', '.join(sorted(forbidden))}."
            " Use Source(..., options=...) for reader options."
        )
    if additional_tables and "additional_data_tables" not in parameters:
        raise TypeError(f"{name} does not support additional tables.")
    _aliases(name, options)
    if name in _MODEL_TASKS and "dictionary_file_path_or_domain" not in options:
        raise TypeError(
            f"{name} requires model=... or dictionary_file_path_or_domain=..."
        )
    with _materialize_source(
        source, additional_tables=additional_tables, connection=connection
    ) as data:
        _input_arguments(name, data, parameters, options)
        paths = _output_arguments(name, output_dir, options)
        inspect.signature(function).bind(**options)
        result = function(**options)
    if result is None and paths:
        return next(iter(paths.values()))
    return result


def _aliases(name: str, options: dict[str, Any]) -> None:
    if "target" in options:
        if name not in {"train_predictor", "train_recoder"}:
            raise TypeError(f"{name} does not accept target.")
        if "target_variable" in options:
            raise TypeError("Specify target or target_variable, not both.")
        options["target_variable"] = options.pop("target")
    if name == "train_predictor" and "target_variable" not in options:
        raise TypeError(
            "Specify target=... (or target='' for unsupervised preparation)."
        )
    if name == "train_recoder":
        options.setdefault("target_variable", "")
    if "model" in options:
        if "dictionary_file_path_or_domain" in options:
            raise TypeError(
                "Specify model or dictionary_file_path_or_domain, not both."
            )
        options["dictionary_file_path_or_domain"] = options.pop("model")
    if name == "evaluate_predictor" and "dictionary_name" in options:
        if "train_dictionary_name" in options:
            raise TypeError(
                "Specify dictionary_name or train_dictionary_name, not both."
            )
        options["train_dictionary_name"] = options.pop("dictionary_name")


def _input_arguments(
    name: str,
    data: Dataset,
    parameters: Mapping[str, inspect.Parameter],
    options: dict[str, Any],
) -> None:
    options["data_table_path"] = data.data_table_path
    for key in ("header_line", "field_separator", "additional_data_tables"):
        if key in parameters:
            options[key] = data.table_args[key]
    if "detect_format" in parameters:
        options["detect_format"] = False
    if "dictionary_file_path_or_domain" in parameters:
        domain = options.setdefault(
            "dictionary_file_path_or_domain", data.dictionary_domain
        )
        if isinstance(domain, PathLike):
            domain = options["dictionary_file_path_or_domain"] = fspath(domain)
        dictionary_name = "dictionary_name"
        if name == "evaluate_predictor":
            dictionary_name = "train_dictionary_name"
        if dictionary_name in parameters and dictionary_name not in options:
            if domain is data.dictionary_domain:
                options[dictionary_name] = data.dictionary_name
            else:
                options[dictionary_name] = _model_dictionary_name(domain)
    if name == "build_dictionary_from_data_table":
        options.setdefault("output_dictionary_name", data.dictionary_name)


def _model_dictionary_name(model: Any) -> str:
    domain = kh.read_dictionary_file(model) if isinstance(model, str) else model
    if not isinstance(domain, kh.DictionaryDomain):
        raise TypeError("model must be a dictionary path or a Khiops DictionaryDomain.")
    roots = [dictionary for dictionary in domain.dictionaries if dictionary.root]
    candidates = roots or list(domain.dictionaries)
    if len(candidates) != 1:
        raise ValueError(
            "Cannot choose a unique model dictionary. Specify dictionary_name "
            "(or train_dictionary_name for evaluation)."
        )
    name: str = candidates[0].name
    return name


def _output_arguments(
    name: str,
    output_dir: str | PathLike[str] | None,
    options: dict[str, Any],
) -> dict[str, str]:
    outputs = _OUTPUTS.get(name, {})
    directory = None
    if any(options.get(key) is None for key in outputs):
        if output_dir is None:
            parent = Path("khiops-results").resolve()
            parent.mkdir(parents=True, exist_ok=True)
            directory = Path(mkdtemp(prefix=f"{name}-", dir=parent))
        else:
            directory = Path(output_dir).expanduser().resolve()
            directory.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, filename in outputs.items():
        path = options.get(key)
        if path is None:
            if directory is None:
                raise RuntimeError("An output directory is required for default paths.")
            path = directory / filename
        paths[key] = options[key] = str(Path(path).expanduser().resolve())
    return paths


build_dictionary_from_data_table: _SourceFunction[str] = _adapt(
    "build_dictionary_from_data_table", "Construit un dictionnaire depuis une source."
)
check_database: _SourceFunction[None] = _adapt(
    "check_database", "Vérifie une source avec son dictionnaire."
)
deploy_coclustering: _SourceFunction[tuple[str, str]] = _adapt(
    "deploy_coclustering", "Déploie un coclustering sur une source."
)
deploy_model: _SourceFunction[str] = _adapt(
    "deploy_model", "Déploie un modèle sur une source et retourne le fichier produit."
)
deploy_predictor_for_metrics: _SourceFunction[str] = _adapt(
    "deploy_predictor_for_metrics", "Déploie un prédicteur pour calculer ses métriques."
)
detect_data_table_format: _SourceFunction[tuple[bool | None, str | None]] = _adapt(
    "detect_data_table_format", "Détecte le format du snapshot TSV matérialisé."
)
evaluate_predictor: _SourceFunction[str] = _adapt(
    "evaluate_predictor", "Évalue un prédicteur sur une source."
)
extract_keys_from_data_table: _SourceFunction[str] = _adapt(
    "extract_keys_from_data_table", "Extrait les clés d'une source."
)
sort_data_table: _SourceFunction[str] = _adapt(
    "sort_data_table", "Trie une source et retourne le fichier produit."
)
train_coclustering: _SourceFunction[str] = _adapt(
    "train_coclustering", "Entraîne un coclustering depuis une source."
)
train_instance_variable_coclustering: _SourceFunction[str] = _adapt(
    "train_instance_variable_coclustering",
    "Entraîne un coclustering instances-variables depuis une source.",
)
train_predictor: _SourceFunction[tuple[str, str | None]] = _adapt(
    "train_predictor", "Entraîne un prédicteur depuis une source."
)
train_recoder: _SourceFunction[tuple[str, str]] = _adapt(
    "train_recoder", "Entraîne un recodeur depuis une source."
)

__all__ = [
    "build_dictionary_from_data_table",
    "check_database",
    "deploy_coclustering",
    "deploy_model",
    "deploy_predictor_for_metrics",
    "detect_data_table_format",
    "evaluate_predictor",
    "extract_keys_from_data_table",
    "sort_data_table",
    "train_coclustering",
    "train_instance_variable_coclustering",
    "train_predictor",
    "train_recoder",
]


def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(kh, name)
