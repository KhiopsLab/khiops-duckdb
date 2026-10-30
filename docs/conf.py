"""Configuration de la documentation Sphinx."""

from importlib.metadata import version as package_version

project = "Khiops DuckDB"
author = "KhiopsLab contributors"
copyright = "2026, KhiopsLab contributors"
release = package_version("khiops-duckdb")
version = release
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.githubpages",
    "sphinx.ext.napoleon",
    "sphinx_copybutton",
    "myst_nb",
]
html_theme = "furo"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/KhiopsLab/khiops-duckdb/",
    "source_branch": "main",
    "source_directory": "docs/",
}
exclude_patterns = ["_build", "**/.ipynb_checkpoints"]
nb_execution_mode = "force"
autodoc_typehints = "description"
