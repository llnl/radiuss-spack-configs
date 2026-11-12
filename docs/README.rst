Building and editing the guide
==============================

The guide uses Sphinx/reStructuredText. Run these commands from the repository
root with Python 3.11 and Graphviz's ``dot`` on PATH:

.. code-block:: bash

   python3 -m venv .venv-docs
   .venv-docs/bin/python -m pip install -r docs/requirements.txt
   .venv-docs/bin/sphinx-build -n -W --keep-going -b html docs/sphinx docs/_build/html
   .venv-docs/bin/sphinx-build -n -W --keep-going -b latex docs/sphinx docs/_build/latex
   .venv-docs/bin/sphinx-build -n -W --keep-going -b linkcheck docs/sphinx docs/_build/linkcheck

Sphinx is pinned to 6.2.1 and the Read the Docs theme to 1.2.2. The strict
commands fail on documentation warnings. Link checking requires network access;
inspect broken-link output separately from service rate limits or unavailable
external hosts. The LaTeX builder generates LaTeX source and PDF figures; with
a TeX installation and ``latexmk``, compile the manual with:

.. code-block:: bash

   make -C docs/_build/latex

The HTML entry point is ``docs/_build/html/index.html``. Read the Docs installs
Graphviz and builds the same Sphinx source. The older ``docs/CMakeLists.txt``
fragment is for a BLT embedding; no top-level CMake project is required to build
this guide.

Figure sources and styling
--------------------------

Edit standalone DOT sources in ``docs/sphinx/figures/``. The Sphinx Graphviz
extension generates SVG for HTML and PDF for LaTeX automatically, using the
shared ``graphviz_dot_args`` in ``conf.py`` for fonts, spacing, borders, and
arrow sizes. Generated assets stay in the build directory and are not committed.
No raster illustration or pre-rendering step is required.

Keep these node styles consistent when adding a figure:

.. list-table:: Visual vocabulary
   :header-rows: 1

   * - Concept
     - Graphviz shape/style
     - Fill
   * - Git repository
     - ``folder``, labeled with repository name
     - ``#e3edf7``
   * - Recipe
     - ``note``, labeled ``package.py``
     - ``#fff2cf``
   * - Configuration
     - ``tab``
     - ``#eee8f5``
   * - Reference or pin
     - Small ``box`` with revision label
     - ``#f7e4e4``
   * - Process or command
     - ``box`` with ``rounded,filled`` style
     - ``#e1f2e8``
   * - Generated artifact or storage output
     - ``parallelogram``
     - ``#dcf2f4``

Use solid arrows for execution/output flow, dashed arrows with ``empty`` heads
for input/dependency relationships, and dotted arrows with ``vee`` heads for
adoption of a revision. Describe relationships in edge labels and supply both
``:caption:`` and ``:alt:`` on every ``graphviz`` directive. Keep diagrams
readable at normal page width and inspect the HTML and PDF renderings.

Editorial maintenance
---------------------

Keep the ordinary workflow in ``developer_workflow``, infrastructure procedures
in ``maintainer_guide`` and ``ci_implementation``, and ownership/precedence in
``reference``. Use document-prefixed automatic section labels to avoid label
collisions, and explicit labels for stable cross-page references.

The former ``user_guide`` and ``developer_guide`` directories were renamed to
``developer_workflow`` and ``maintainer_guide``, respectively. The old URLs are
not redirected; update links in consuming projects to use the new paths.
Existing section anchors remain available at the new URLs.

Keep maintained design contracts and their rationale in
``maintainer_guide/design_choices``. Record dated audit evidence, validation
results and engineering follow-ups in the pull request description.
