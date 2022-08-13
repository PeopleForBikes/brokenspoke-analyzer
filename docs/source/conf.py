# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))
from importlib import metadata

# -- Project information -----------------------------------------------------

project = "Brokenspoke Analyzer"
copyright = "2022, PeopleForBikes"
author = "PeopleForBikes"
package = "brokenspoke-analyzer"

# The full version, including alpha/beta/rc tags
release = metadata.version(package)


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = ["myst_parser", "sphinx_copybutton", "sphinx.ext.githubpages"]
myst_enable_extensions = [
    "amsmath",
    "colon_fence",
    "deflist",
    "dollarmath",
    "fieldlist",
    "html_admonition",
    "html_image",
    "replacements",
    "smartquotes",
    "strikethrough",
    "substitution",
    "tasklist",
]


# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "furo"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

html_theme_options = {
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/PeopleForBikes/brokenspoke-analyzer",
            "html": """
                <svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16">
                    <path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path>
                </svg>
            """,
            "class": "",
        },
    ],
    "light_css_variables": {
        # for main text and headings
        "color-foreground-primary": "#8B8A8D",
        # for secondary text
        "color-foreground-secondary": "#009EDB",
        # for muted text
        "color-foreground-muted": "#D71920",
        # for content borders
        "color-foreground-border": "#878787",
        # for content
        "color-background-primary": "#fcfaf6",
        # for navigation + ToC
        "color-background-secondary": "#fcfaf6",
        # for navigation-item hover
        "color-background-hover": "#effaffff",
        "color-background-hover--transparent": "#effaff00",
        # for UI borders
        "color-background-border": "#eeebee",
        # for "background" items (eg: copybutton)
        "color-background-item": "#ccc",
        # Brand colors
        "color-brand-primary": "#009EDB",
        "color-brand-content": "#8B8A8D",
        # Fonts
        "font-stack": 'Montserrat, "Open Sans", Helvetica, Arial, sans-serif',
    },
    "dark_css_variables": {
        # for main text and headings
        "color-foreground-primary": "#8B8A8D",
        # for secondary text
        "color-foreground-secondary": "#009EDB",
        # for muted text
        "color-foreground-muted": "#D71920",
        # for content borders
        "color-foreground-border": "878787",
        # for content
        "color-background-primary": "#00263E",
        # for navigation + ToC
        "color-background-secondary": "#00263E",
        # for navigation-item hover
        "color-background-hover": "#1e2124ff",
        "color-background-hover--transparent": "#1e212400",
        # for UI borders
        "color-background-border": "#8B8A8D",
        # for "background" items (eg: copybutton)
        "color-background-item": "#ccc",
        # Brand colors
        "color-brand-primary": "#009EDB",
        "color-brand-content": "#009EDB",
        # Fonts
        "font-stack": 'Montserrat, "Open Sans", Helvetica, Arial, sans-serif',
    },
}
