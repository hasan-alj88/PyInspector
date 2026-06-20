# 📦 PyInspector

**PyInspector** is a command-line interface (CLI) tool designed to statically inspect other Python packages inside isolated, ephemeral `uv` virtual environments. It extracts module structures, classes, functions, and parameter signatures without importing or executing any of the target package's code.

---

## 🚀 Key Features

* **Ephemeral Isolation & .venv Reuse**: Automatically provisions a temporary `uv` virtual environment to install and inspect the package, cleaning it up upon completion. If a local directory already contains a `.venv`, PyInspector automatically reuses it to skip the overhead of environment creation and installation.
* **Static AST Traversal**: Parses source code files and type stub files (`.pyi`) statically using Python's `ast` module. Safe to run on untrusted code (no execution) and supports C++ (`pybind11`) and Rust (`maturin`) binary extensions that distribute stubs.
* **Multi-Version Python Execution**: Inspect packages under different Python versions (e.g. Python 3.11, 3.10) dynamically. `uv` handles Python version downloads automatically.
* **API Version Diffing**: Compare two versions of a package to see added, removed, or modified classes, methods, and functions, alongside their `requires-python` metadata.
* **Symlink & Cycle Detection**: Traverses symlinks safely with canonical path tracking (`os.path.realpath`). Detects recursive loops or duplicate modules, short-circuiting traversal and labeling loops clearly in outputs.
* **Visual ASCII Tree**: Prints gorgeous color-coded Unicode/ASCII trees of package APIs using `rich`. Also supports exports to **JSON** and **YAML**.
* **OOP UML Relations Mapping**: Map inheritance and composition hierarchies starting from the root `object`, regardless of module file placement. Extracts class properties/attributes (via `__init__` and `@property`/`@cached_property` getters) along with their type hints. Exports to ASCII tree, Mermaid class diagram, and Rich tables.

---

## 🛠️ Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed on your system.

Clone the project and install it in editable mode:
```bash
# Install package dependencies
uv sync
```

You can now run commands using `uv run pyinspector` or run the CLI globally by building/installing the package.

---

## 📖 CLI Command Manual

PyInspector provides five primary commands: `inspect`, `search`, `compare`, `oop`, and `functions`.

### 1. `inspect`
Statically inspects a package and visualizes its structure.

**Syntax**:
```bash
uv run pyinspector inspect <package_spec> [options]
```

* **`package_spec`**: The package identifier. Can be a PyPI name (`requests`), a versioned PyPI package (`requests==2.31.0`), or a local folder path (`./my_package`).
* **`--python TEXT`**: Specific Python version constraint to build the environment with (e.g., `3.10`, `3.11`).
* **`--version TEXT`**: Alternative way to specify the PyPI package version.
* **`--format [tree|json|yaml]`**: Sets output type (Default: `tree`).
* **`--output FILE`**: Saves JSON or YAML outputs directly to a file.
* **`--private`**: Includes private and protected members (starting with `_`) in the output tree. Special methods like `__init__` are always included.
* **`--depth INTEGER`**: Restricts module recursion depth.
* **`--no-build-isolation`**: Disables build isolation when installing local packages, allowing access to packages installed in the system/parent environment.

**Example**:
```bash
uv run pyinspector inspect requests --version 2.31.0 --depth 2
```

---

### 2. `search`
Searches for classes, functions, or methods inside a package.

**Syntax**:
```bash
uv run pyinspector search <package_spec> <query> [options]
```

* **`package_spec`**: PyPI package name, spec, or local directory path.
* **`query`**: Case-insensitive search string matching class, function, or method names.
* **`--python TEXT`**: Specific Python version constraint.
* **`--private`**: Includes private elements in the search scope.
* **`--no-build-isolation`**: Disables build isolation when installing local packages.

**Example**:
```bash
uv run pyinspector search scipy Session --python 3.11
```

---

### 3. `compare`
Compares the API structure of two versions of a package and retrieves Python compatibility constraints.

**Syntax**:
```bash
uv run pyinspector compare <package_name> <version_a> <version_b> [options]
```

* **`package_name`**: PyPI name of the package.
* **`version_a`**: First target version (e.g. `2.31.0`) or local directory path.
* **`version_b`**: Second target version (e.g. `2.32.0`) or local directory path.
* **`--python TEXT`**: Specific Python version constraint to run both environments under.
* **`--no-build-isolation`**: Disables build isolation when installing local packages.

**Example**:
```bash
uv run pyinspector compare requests 2.31.0 2.32.0
```

---

### 4. `oop`
Maps class hierarchies, composition structures, and properties of a package under the root `object`. Statically extracts attributes declared on `self` inside `__init__` constructor as well as getters decorated with `@property`/`@cached_property`, retrieving any type annotations.

**Syntax**:
```bash
uv run pyinspector oop <package_spec> [options]
```

* **`package_spec`**: PyPI package name, version spec, or local folder path.
* **`--python TEXT`**: Specific Python version constraint.
* **`--format [tree|mermaid|table]`**: Visual representation mode (Default: `tree`).
* **`--include-external`**: Includes external (e.g. standard library or third-party) base classes in the tree.
* **`--no-composition`**: Excludes composition association links in Mermaid, and hides `, composes <type>` suffixes from properties in tree and table formats.
* **`--no-build-isolation`**: Disables build isolation when installing local packages.

**Example**:
```bash
uv run pyinspector oop requests --format mermaid
```

---

### 5. `functions`
Displays top-level (plain) functions and their signatures grouped by their module/file location in a clean, pruned hierarchical tree (modules without plain functions are pruned).

**Syntax**:
```bash
uv run pyinspector functions <package_spec> [options]
```

* **`package_spec`**: PyPI package name, spec, or local directory path.
* **`--python TEXT`**: Specific Python version constraint.
* **`--private`**: Includes private functions (starting with `_`) in the tree.
* **`--depth INTEGER`**: Restricts module recursion depth.
* **`--no-build-isolation`**: Disables build isolation when installing local packages.

**Example**:
```bash
uv run pyinspector functions requests --private
```

---

## 💡 Practical Workflows & Examples

### A. Inspecting a Local Directory
To inspect a local package checkout (e.g., prior to publishing) without installing it globally:
```bash
uv run pyinspector inspect ./my_library
```
If PyInspector detects an existing local virtual environment (`.venv`) inside the target directory, it automatically reuses that environment's Python executable and installed dependencies instead of constructing a new temporary environment. This significantly speeds up inspection on already-configured local projects.

### B. Python Version Compatibility Checks
If you want to verify if a package installs and parses correctly under Python 3.10:
```bash
uv run pyinspector inspect scipy --version 1.10.0 --python 3.10
```
This forces `uv` to instantiate Python 3.10 inside the temp directory, install SciPy, and run AST parsing.

### C. Finding API Breaking Changes
To quickly see functions/methods modified or deleted between two package releases:
```bash
uv run pyinspector compare requests 2.31.0 2.32.3
```
This prints:
* Python version constraint changes (`requires-python` metadata fetched from PyPI).
* Structural summary (metric totals).
* Names of added/removed modules, classes, and methods.
* Side-by-side signature comparison for any modified functions.

---

## 🏗️ Technical Architecture

PyInspector is modularly structured to keep logic separate and maintainable:

```
src/pyinspector/
├── __init__.py
├── main.py (CLI orchestrator entrypoint)
├── env/
│   ├── manager.py (manages temp directories, uv subprocesses, and cleans env vars)
│   └── locate_helper.py (run inside subprocesses to find package installation locations)
├── analyzer/
│   ├── parser.py (handles AST parsing, bases/composition extraction, and cycle detection)
│   └── oop.py (structures class inheritance forest under 'object')
├── viewer/
│   └── formatter.py (generates colored Rich Trees and exports data to JSON/YAML)
├── comparer/
│   └── diff.py (performs API structural comparison and retrieves requires-python specs)
└── cli/
    └── commands.py (defines Click inputs and routes actions)
```

### Cleansing Subprocess Environments
When executing inside `uv run`, parent virtualenv paths are present in `os.environ["VIRTUAL_ENV"]`. PyInspector's environment manager automatically pops this variable in subprocesses, ensuring `uv` installs packages strictly inside the temporary virtual environments.

### Local Virtual Environment Reuse
When analyzing local directories that already contain a `.venv` directory, PyInspector skips temporary environment setup and package installation entirely. Instead, it directly uses the Python executable located inside the local `.venv`. If the project is not installed as a distribution in that virtual environment, the locate helper dynamically falls back to scanning the project's root and `src/` directories to detect package subdirectories (containing `__init__.py`) or standalone modules, injecting their directories into `sys.path` to resolve them.

### Type Stub Prioritization (.pyi)
For packages with compiled binary modules (such as C++ extensions using Pybind11 or Rust extensions using Maturin), PyInspector supports scanning and parsing `.pyi` type stub files statically. When a directory contains both a `.py` and a `.pyi` file for the same module name, PyInspector automatically prioritizes the `.pyi` stub to extract public API signatures.

### Strict Import Scope Isolation
PyInspector operates strictly on the local codebase directory of the target package. 
* Any `import` or `from ... import` statements encountered during static AST analysis are parsed strictly as plain-text signatures for methods and functions.
* PyInspector **never follows or traverses imports** to external packages or dependencies (e.g. standard library or PyPI packages).
* This boundary model prevents recursive loops across dependencies, restricts computation strictly to the package's repo, and guarantees execution safety.

---

## 🧪 Running Unit Tests

PyInspector uses Python's standard `unittest` framework. The test cases install and inspect SciPy under different environments to verify the engine:

```bash
uv run python -m unittest discover -s tests
```
