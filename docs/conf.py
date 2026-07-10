#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import tomllib

sys.path.insert(0, os.path.abspath(".."))

_pyproject_path = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")
with open(_pyproject_path, "rb") as _f:
    _pyproject = tomllib.load(_f)
_project_title = _pyproject["project"]["name"]
_project_version = _pyproject["project"]["version"]
_project_author = _pyproject["project"]["authors"][0]["name"]

# -- General configuration ------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinxcontrib.httpdomain",
    "sphinxcontrib.autohttp.flask",
    # Needed so @celery.task-decorated functions in tasks.py get autodoc'd.
    "celery.contrib.sphinx",
]

templates_path = ["_templates"]
source_suffix = ".rst"
master_doc = "index"

project = _project_title
_this_year = str(__import__("datetime").datetime.now().year)
copyright = f"2014\u2013{_this_year} SynoCommunity"

version = _project_version.split("-")[0]
release = _project_version

exclude_patterns = ["_build"]
pygments_style = "sphinx"

# -- Options for HTML output ----------------------------------------------

html_theme = "pydata_sphinx_theme"
html_theme_options = {
    "navigation_depth": 2,
    "show_nav_level": 2,
    "navigation_with_keys": True,
    "use_edit_page_button": True,
    # No page links in navbar — navigation is entirely in the left sidebar.
    "navbar_center": [],
    "navbar_align": "left",
    # Omit search-field since RTD injects its own search addon.
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/SynoCommunity/spkrepo",
            "icon": "fa-brands fa-github",
        },
    ],
    "secondary_sidebar_items": ["page-toc"],
    "logo": {
        "text": _project_title,
    },
    "primary_sidebar_end": [],
}
html_context = {
    "github_user": "SynoCommunity",
    "github_repo": "spkrepo",
    "github_version": "main",
    "doc_path": "docs",
}

html_static_path = ["_static"]
html_css_files = ["custom.css"]

html_sidebars = {
    "**": ["globaltoc.html"],
}

htmlhelp_basename = _project_title + "doc"

# -- Options for LaTeX output ---------------------------------------------

latex_elements = {}

latex_documents = [
    (
        "index",
        "%s.tex" % _project_title,
        "%s Documentation" % _project_title,
        _project_author,
        "manual",
    ),
]

# -- Options for manual page output ---------------------------------------

man_pages = [
    (
        "index",
        _project_title,
        "%s Documentation" % _project_title,
        [_project_author],
        1,
    )
]

# -- Options for Texinfo output -------------------------------------------

texinfo_documents = [
    (
        "index",
        _project_title,
        "%s Documentation" % _project_title,
        _project_author,
        _project_title,
        "Synology Package Repository",
        "Miscellaneous",
    ),
]

# -- Options for Epub output ----------------------------------------------

epub_title = _project_title
epub_author = _project_author
epub_publisher = _project_author
epub_copyright = copyright
epub_exclude_files = ["search.html"]
