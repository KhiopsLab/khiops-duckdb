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
html_title = "Khiops DuckDB"
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
html_theme_options = {
    "source_repository": "https://github.com/KhiopsLab/khiops-duckdb/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": "#f16e00",
        "color-brand-content": "#000000",
        "color-brand-visited": "#000000",
        "color-foreground-primary": "#000000",
        "color-foreground-secondary": "#666666",
        "color-foreground-muted": "#666666",
        "color-background-primary": "#ffffff",
        "color-background-secondary": "#eeeeee",
        "color-background-hover": "#dddddd",
        "color-background-border": "#cccccc",
        "color-sidebar-background": "#fafafa",
        "color-sidebar-link-text--top-level": "var(--color-brand-content)",
        "color-toc-item-text--active": "var(--color-brand-content)",
        "color-admonition-title--note": "var(--color-brand-primary)",
        "color-admonition-title-background--note": "var(--color-background-secondary)",
        "color-inline-code-background": "var(--color-background-secondary)",
        "color-inline-code-text": "var(--color-foreground-primary)",
        "color-code-background": "var(--color-background-secondary)",
        "font-stack": "'Helvetica Neue', Helvetica, Arial, sans-serif",
        "font-stack--monospace": "ui-monospace, SFMono-Regular, Consolas, monospace",
    },
    "dark_css_variables": {
        "color-brand-primary": "#ff7900",
        "color-brand-content": "#ffffff",
        "color-brand-visited": "#ffffff",
        "color-foreground-primary": "#ffffff",
        "color-foreground-secondary": "#999999",
        "color-foreground-muted": "#999999",
        "color-background-primary": "#141414",
        "color-background-secondary": "#333333",
        "color-background-hover": "#666666",
        "color-background-border": "#666666",
        "color-sidebar-background": "#000000",
        "color-sidebar-link-text--top-level": "var(--color-brand-content)",
        "color-toc-item-text--active": "var(--color-brand-content)",
        "color-admonition-title--note": "var(--color-brand-primary)",
        "color-admonition-title-background--note": "var(--color-background-secondary)",
        "color-inline-code-background": "var(--color-background-secondary)",
        "color-inline-code-text": "var(--color-foreground-primary)",
        "color-code-background": "var(--color-background-secondary)",
        "font-stack": "'Helvetica Neue', Helvetica, Arial, sans-serif",
        "font-stack--monospace": "ui-monospace, SFMono-Regular, Consolas, monospace",
    },
}
exclude_patterns = ["_build", "**/.ipynb_checkpoints"]
nb_execution_mode = "force"
autodoc_typehints = "description"
add_module_names = False
