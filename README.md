# 📦 PyInspector

**PyInspector** is a command-line interface (CLI) tool designed to statically inspect other Python packages inside isolated, ephemeral `uv` virtual environments. It extracts module structures, classes, functions, and parameter signatures without importing or executing any of the target package's code.

---

## 🚀 Key Features

* **Ephemeral Isolation**: Uses `uv` to automatically provision a temporary virtual environment, install the package, and inspect it. Cleaned up immediately on completion or error.
* **Static AST Traversal**: Parses source code files using Python's `ast` module. Safe to run on untrusted code (no `__init__.py` or module-level execution).
* **Multi-Version Python Execution**: Inspect packages under different Python versions (e.g. Python 3.11, 3.10) dynamically. `uv` handles Python version downloads automatically.
* **API Version Diffing**: Compare two versions of a package to see added, removed, or modified classes, methods, and functions, alongside their `requires-python` metadata.
* **Symlink & Cycle Detection**: Traverses symlinks safely with canonical path tracking (`os.path.realpath`). Detects recursive loops or duplicate modules, short-circuiting traversal and labeling loops clearly in outputs.
* **Visual ASCII Tree**: Prints gorgeous color-coded Unicode/ASCII trees of package APIs using `rich`. Also supports exports to **JSON** and **YAML**.

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

PyInspector provides three primary commands: `inspect`, `search`, and `compare`.

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

**Example**:
```bash
uv run pyinspector compare requests 2.31.0 2.32.0
```

---

## 💡 Practical Workflows & Examples

### A. Inspecting a Local Directory
To inspect a local package checkout (e.g., prior to publishing) without installing it globally:
```bash
uv run pyinspector inspect ./my_library
```

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
│   └── parser.py (handles AST parsing, unparsing parameter signatures, and docstrings)
├── viewer/
│   └── formatter.py (generates colored Rich Trees and exports data to JSON/YAML)
├── comparer/
│   └── diff.py (performs API structural comparison and retrieves requires-python specs)
└── cli/
    └── commands.py (defines Click inputs and routes actions)
```

### Cleansing Subprocess Environments
When executing inside `uv run`, parent virtualenv paths are present in `os.environ["VIRTUAL_ENV"]`. PyInspector's environment manager automatically pops this variable in subprocesses, ensuring `uv` installs packages strictly inside the temporary virtual environments.

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
