import unittest
import os
from click.testing import CliRunner
from pyinspector.cli import cli
from pyinspector.env import temp_env

class TestPyInspector(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_temp_env_scipy(self):
        """Test that temp_env correctly installs and resolves scipy."""
        with temp_env("scipy==1.10.0", python_version="3.11") as modules:
            self.assertIn("scipy", modules)
            pkg_path = modules["scipy"]
            self.assertTrue(os.path.exists(pkg_path))

    def test_cli_inspect_scipy(self):
        """Test inspect command on scipy."""
        result = self.runner.invoke(cli, ["inspect", "scipy==1.10.0", "--python", "3.11", "--depth", "1"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("scipy", result.output)

    def test_cli_search_scipy(self):
        """Test search command on scipy."""
        # Search for a sub-module/class containing 'cluster' in scipy
        result = self.runner.invoke(cli, ["search", "scipy==1.10.0", "cluster", "--python", "3.11"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("cluster", result.output)

    def test_cli_compare_scipy(self):
        """Test compare command comparing two scipy versions."""
        result = self.runner.invoke(cli, ["compare", "scipy", "1.10.0", "1.10.1", "--python", "3.11"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("API Comparison", result.output)
        self.assertIn("Requires Python Constraint", result.output)

    def test_cli_options_no_build_isolation(self):
        """Test that subcommands accept the --no-build-isolation option."""
        result = self.runner.invoke(cli, ["inspect", "--help"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("--no-build-isolation", result.output)
        
        result_oop = self.runner.invoke(cli, ["oop", "--help"])
        self.assertEqual(result_oop.exit_code, 0)
        self.assertIn("--no-build-isolation", result_oop.output)

    def test_cycle_detection_symlinks(self):
        """Test that analyze_package correctly detects and marks folder and file loops."""
        import tempfile
        import shutil
        from pyinspector.analyzer.parser import analyze_package
        
        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-loop-")
        try:
            # Create a simple python package structure
            os.makedirs(os.path.join(temp_pkg, "sub"))
            
            with open(os.path.join(temp_pkg, "__init__.py"), "w") as f:
                f.write("# pkg\n")
            with open(os.path.join(temp_pkg, "core.py"), "w") as f:
                f.write("def func_core(): pass\n")
            with open(os.path.join(temp_pkg, "sub", "__init__.py"), "w") as f:
                f.write("# sub\n")
            with open(os.path.join(temp_pkg, "sub", "helper.py"), "w") as f:
                f.write("def func_helper(): pass\n")
                
            # Create a directory symlink loop: sub/loop -> top
            os.symlink(temp_pkg, os.path.join(temp_pkg, "sub", "loop"))
            
            # Create a file symlink loop/duplicate: sub/dup.py -> core.py
            os.symlink(os.path.join(temp_pkg, "core.py"), os.path.join(temp_pkg, "sub", "dup.py"))
            
            # Analyze
            pkg_info = analyze_package("testpkg", temp_pkg)
            
            # Verify the directory loop was detected
            self.assertIn("testpkg.sub.loop", pkg_info.modules)
            self.assertTrue(pkg_info.modules["testpkg.sub.loop"].is_recursive)
            self.assertEqual(pkg_info.modules["testpkg.sub.loop"].points_to, "testpkg")
            
            # Verify the file loop/duplicate was detected
            self.assertIn("testpkg.sub.dup", pkg_info.modules)
            self.assertTrue(pkg_info.modules["testpkg.sub.dup"].is_recursive)
            self.assertEqual(pkg_info.modules["testpkg.sub.dup"].points_to, "testpkg.core")
            
        finally:
            try:
                os.unlink(os.path.join(temp_pkg, "sub", "loop"))
                os.unlink(os.path.join(temp_pkg, "sub", "dup.py"))
            except Exception:
                pass
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_import_scope_isolation(self):
        """Test that import statements to external dependencies are strictly ignored and not followed."""
        import tempfile
        import shutil
        from pyinspector.analyzer.parser import analyze_package
        
        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-scope-")
        try:
            # Create a package with external imports
            os.makedirs(os.path.join(temp_pkg, "sub"))
            
            with open(os.path.join(temp_pkg, "__init__.py"), "w") as f:
                f.write("import os\nimport sys\nimport requests\n")
            with open(os.path.join(temp_pkg, "sub", "__init__.py"), "w") as f:
                f.write("# sub\n")
            with open(os.path.join(temp_pkg, "sub", "api.py"), "w") as f:
                f.write("from scipy import stats\nimport click\n")
                
            pkg_info = analyze_package("isolationpkg", temp_pkg)
            
            # Modules parsed must be exactly local files
            expected_modules = {"isolationpkg", "isolationpkg.sub", "isolationpkg.sub.api"}
            self.assertEqual(set(pkg_info.modules.keys()), expected_modules)
            
            # External dependencies must NOT be traversed or counted as package modules
            self.assertNotIn("requests", pkg_info.modules)
            self.assertNotIn("scipy", pkg_info.modules)
            self.assertNotIn("click", pkg_info.modules)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_oop_relations(self):
        """Test build_oop_graph and oop CLI formatting (tree, mermaid, table) on local code."""
        import tempfile
        import shutil
        from pyinspector.analyzer.parser import analyze_package
        from pyinspector.analyzer.oop import build_oop_graph
        
        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-oop-")
        try:
            # Create a simple python package with inheritance & composition inside a subdirectory
            pkg_src_dir = os.path.join(temp_pkg, "ooppkg")
            os.makedirs(pkg_src_dir)
            with open(os.path.join(pkg_src_dir, "__init__.py"), "w") as f:
                f.write("""
class Animal:
    def __init__(self):
        self.age: int = 10

class Dog(Animal):
    @property
    def sound(self) -> str:
        return "bark"

class Owner:
    def __init__(self):
        self.pet = Dog()
""")
            with open(os.path.join(temp_pkg, "setup.py"), "w") as f:
                f.write("""
from setuptools import setup, find_packages
setup(name='ooppkg', version='0.1.0', packages=find_packages())
""")
                
            pkg_info = analyze_package("ooppkg", pkg_src_dir)
            
            # Build OOP graph
            root_node = build_oop_graph(pkg_info, include_external=False)
            
            # object has subclasses Animal and Owner
            self.assertEqual(root_node.name, "object")
            sub_names = {s.name for s in root_node.subclasses}
            self.assertIn("Animal", sub_names)
            self.assertIn("Owner", sub_names)
            
            # Animal has subclass Dog
            animal_node = next(s for s in root_node.subclasses if s.name == "Animal")
            self.assertEqual(len(animal_node.subclasses), 1)
            self.assertEqual(animal_node.subclasses[0].name, "Dog")
            
            # Verify property on Animal (via init)
            animal_props = {p.name: p for p in animal_node.class_info.properties}
            self.assertIn("age", animal_props)
            self.assertEqual(animal_props["age"].type_hint, "int")
            self.assertEqual(animal_props["age"].source, "init")
            
            # Verify property on Dog (via @property getter)
            dog_node = animal_node.subclasses[0]
            dog_props = {p.name: p for p in dog_node.class_info.properties}
            self.assertIn("sound", dog_props)
            self.assertEqual(dog_props["sound"].type_hint, "str")
            self.assertEqual(dog_props["sound"].source, "property")
            
            # Owner has composition targeting Dog
            owner_node = next(s for s in root_node.subclasses if s.name == "Owner")
            self.assertIn("pet", owner_node.resolved_composition)
            self.assertEqual(owner_node.resolved_composition["pet"].name, "Dog")
            
            # Test CLI invocations
            # 1. tree
            res_tree = self.runner.invoke(cli, ["oop", temp_pkg, "--format", "tree"])
            self.assertEqual(res_tree.exit_code, 0)
            self.assertIn("Animal", res_tree.output)
            self.assertIn("Dog", res_tree.output)
            self.assertNotIn("✦ composes Dog (as pet)", res_tree.output)
            self.assertIn("✦ property: pet: Dog (via init, composes Dog)", res_tree.output)
            self.assertIn("✦ property: age: int (via init, composes int)", res_tree.output)
            self.assertIn("✦ property: sound: str (via property)", res_tree.output)
            
            # 2. mermaid
            res_mermaid = self.runner.invoke(cli, ["oop", temp_pkg, "--format", "mermaid"])
            self.assertEqual(res_mermaid.exit_code, 0)
            self.assertIn("Animal <|-- Dog", res_mermaid.output)
            self.assertIn("Owner *-- Dog : pet", res_mermaid.output)
            self.assertIn("Animal : +age : int (via init, composes int)", res_mermaid.output)
            self.assertIn("Dog : +sound : str (via property)", res_mermaid.output)
            self.assertIn("Owner : +pet : Dog (via init, composes Dog)", res_mermaid.output)
            
            # 3. table
            res_table = self.runner.invoke(cli, ["oop", temp_pkg, "--format", "table"])
            self.assertEqual(res_table.exit_code, 0)
            self.assertIn("Animal", res_table.output)
            self.assertIn("ooppkg", res_table.output)
            self.assertIn("age: int", res_table.output)
            self.assertIn("Dog", res_table.output)
            self.assertIn("sound: str", res_table.output)
            self.assertIn("Owner", res_table.output)
            self.assertIn("pet: Dog", res_table.output)
            self.assertIn("composes", res_table.output)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_pyi_stub_priority(self):
        """Test that analyze_package prioritized .pyi stubs over .py source files when both exist."""
        import tempfile
        import shutil
        from pyinspector.analyzer.parser import analyze_package
        
        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-pyi-")
        try:
            # Create core.py (source implementation)
            with open(os.path.join(temp_pkg, "core.py"), "w") as f:
                f.write("""
class MyClass:
    def implementation_only(self):
        pass
""")
            # Create core.pyi (stub interface with properties)
            with open(os.path.join(temp_pkg, "core.pyi"), "w") as f:
                f.write("""
class MyClass:
    age: int
    def stub_only(self) -> str: ...
""")
            # Analyze
            pkg_info = analyze_package("stubpkg", temp_pkg)
            
            # Verify that only stubpkg.core was parsed, and its source path is core.pyi
            self.assertIn("stubpkg.core", pkg_info.modules)
            mod_info = pkg_info.modules["stubpkg.core"]
            self.assertTrue(mod_info.relative_path.endswith("core.pyi"))
            
            # Verify class structure is from .pyi
            self.assertEqual(len(mod_info.classes), 1)
            cls_info = mod_info.classes[0]
            self.assertEqual(cls_info.name, "MyClass")
            
            # It should have age property (from .pyi)
            prop_names = {p.name for p in cls_info.properties}
            self.assertIn("age", prop_names)
            
            # It should have stub_only method (from .pyi), not implementation_only
            method_names = {m.name for m in cls_info.methods}
            self.assertIn("stub_only", method_names)
            self.assertNotIn("implementation_only", method_names)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_local_venv_reuse(self):
        """Test that temp_env reuses an existing local .venv if present."""
        import tempfile
        import shutil
        import sys
        
        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-local-venv-")
        try:
            # Create a dummy python package structure
            os.makedirs(os.path.join(temp_pkg, "dummy"))
            with open(os.path.join(temp_pkg, "dummy", "__init__.py"), "w") as f:
                f.write("VERSION = '1.0.0'\n")
                
            # Create dummy .venv structure
            venv_bin = os.path.join(temp_pkg, ".venv", "bin")
            os.makedirs(venv_bin)
            
            # Symlink python to sys.executable
            python_symlink = os.path.join(venv_bin, "python")
            os.symlink(sys.executable, python_symlink)
            
            # Run temp_env on the local directory
            from pyinspector.env import temp_env
            with temp_env(temp_pkg) as modules:
                self.assertIn("dummy", modules)
                self.assertEqual(modules["dummy"], os.path.abspath(os.path.join(temp_pkg, "dummy")))
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_functions_explorer(self):
        """Test that the functions explorer properly renders and prunes the module tree."""
        import tempfile
        import shutil
        import io
        from contextlib import redirect_stdout
        from pyinspector.analyzer import analyze_package
        from pyinspector.viewer import render_functions_tree

        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-functions-")
        try:
            # 1. Create package structure
            # module_a.py has top-level function and class
            with open(os.path.join(temp_pkg, "module_a.py"), "w") as f:
                f.write("def hello(name: str) -> None:\n    pass\n\nclass MyClass:\n    def method(self):\n        pass\n")

            # module_b.py has only class (should be pruned)
            with open(os.path.join(temp_pkg, "module_b.py"), "w") as f:
                f.write("class EmptyClass:\n    pass\n")

            # subpkg/module_c.py has top-level function
            os.makedirs(os.path.join(temp_pkg, "subpkg"))
            with open(os.path.join(temp_pkg, "subpkg", "__init__.py"), "w") as f:
                f.write("# init\n")
            with open(os.path.join(temp_pkg, "subpkg", "module_c.py"), "w") as f:
                f.write("def nested_func(x: int) -> int:\n    return x\n")

            # 2. Analyze the package
            pkg_info = analyze_package("testpkg", temp_pkg)

            # 3. Capture output of render_functions_tree
            f_out = io.StringIO()
            with redirect_stdout(f_out):
                render_functions_tree(pkg_info)
            output = f_out.getvalue()

            # 4. Assertions
            # hello and nested_func should be present
            self.assertIn("hello", output)
            self.assertIn("nested_func", output)
            # File paths should be displayed
            self.assertIn("module_a.py", output)
            self.assertIn("module_c.py", output)
            # MyClass and EmptyClass/module_b should NOT be present (pruned)
            self.assertNotIn("MyClass", output)
            self.assertNotIn("EmptyClass", output)
            self.assertNotIn("module_b", output)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_stdlib_import_shadowing(self):
        """Test that local directory paths that match stdlib module names (like 'code') do not resolve to stdlib."""
        import tempfile
        import shutil
        from pyinspector.env import temp_env
        
        # Create a temp directory
        temp_dir = tempfile.mkdtemp()
        try:
            # Create a folder named 'code' inside it
            code_dir = os.path.join(temp_dir, "code")
            os.makedirs(code_dir)
            
            # Create a minimal pyproject.toml
            with open(os.path.join(code_dir, "pyproject.toml"), "w") as f:
                f.write("""[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "code"
version = "0.1.0"
""")
            
            # Add a valid local module 'real_module' inside 'code' directory
            os.makedirs(os.path.join(code_dir, "real_module"))
            with open(os.path.join(code_dir, "real_module", "__init__.py"), "w") as f:
                f.write("X = 1\n")
                
            with temp_env(code_dir) as modules:
                # 'real_module' should be found, but stdlib 'code' should NOT be in modules
                self.assertIn("real_module", modules)
                self.assertNotIn("code", modules)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_function_deprecation(self):
        """Test that deprecation is statically detected via decorators, body warning calls, and docstrings."""
        import tempfile
        import shutil
        import io
        from contextlib import redirect_stdout
        from pyinspector.analyzer import analyze_package
        from pyinspector.viewer import render_rich_tree

        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-deprecate-")
        try:
            # Create a module with various deprecation patterns
            with open(os.path.join(temp_pkg, "dep_mod.py"), "w") as f:
                f.write("""
@deprecated("use new_f1")
def f1():
    pass

def f2():
    import warnings
    warnings.warn("f2 is deprecated: use new_f2 instead", DeprecationWarning)

def f3():
    \"\"\"
    A standard helper.
    
    Deprecated: use new_f3.
    \"\"\"
    pass

class MyClass:
    @custom_deprecated("class method deprecated")
    def m1(self):
        pass
""")
            pkg_info = analyze_package("testpkg", temp_pkg)
            
            # 1. Assert parser values
            self.assertIn("testpkg.dep_mod", pkg_info.modules)
            mod_info = pkg_info.modules["testpkg.dep_mod"]
            
            # Find functions
            f1_info = next(f for f in mod_info.functions if f.name == "f1")
            f2_info = next(f for f in mod_info.functions if f.name == "f2")
            f3_info = next(f for f in mod_info.functions if f.name == "f3")
            
            # Verify f1 (decorator)
            self.assertTrue(f1_info.is_deprecated)
            self.assertEqual(f1_info.deprecation_reason, "use new_f1")
            
            # Verify f2 (body warning)
            self.assertTrue(f2_info.is_deprecated)
            self.assertEqual(f2_info.deprecation_reason, "f2 is deprecated: use new_f2 instead")
            
            # Verify f3 (docstring)
            self.assertTrue(f3_info.is_deprecated)
            self.assertEqual(f3_info.deprecation_reason, "use new_f3.")
            
            # Verify class method m1
            cls_info = next(c for c in mod_info.classes if c.name == "MyClass")
            m1_info = next(m for m in cls_info.methods if m.name == "m1")
            self.assertTrue(m1_info.is_deprecated)
            self.assertEqual(m1_info.deprecation_reason, "class method deprecated")
            
            # 2. Assert rich tree rendering contains warnings
            f_out = io.StringIO()
            with redirect_stdout(f_out):
                render_rich_tree(pkg_info)
            output = f_out.getvalue()
            
            self.assertIn("⚠️  (deprecated: use new_f1)", output)
            self.assertIn("⚠️  (deprecated: f2 is deprecated: use new_f2 instead)", output)
            self.assertIn("⚠️  (deprecated: use new_f3.)", output)
            self.assertIn("⚠️  (deprecated: class method deprecated)", output)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

    def test_init_config_warnings(self):
        """Test that unexposed classes/functions and items missing from __all__ are correctly detected and printed with warnings."""
        import tempfile
        import shutil
        import io
        from contextlib import redirect_stdout
        from pyinspector.analyzer.parser import analyze_package
        from pyinspector.viewer import render_rich_tree

        temp_pkg = tempfile.mkdtemp(prefix="pyinspector-test-initcheck-")
        try:
            # Create root __init__.py
            with open(os.path.join(temp_pkg, "__init__.py"), "w") as f:
                f.write("# root package\n")

            # 1. Test explicit imports in subpackage
            os.makedirs(os.path.join(temp_pkg, "sub"))
            with open(os.path.join(temp_pkg, "sub", "__init__.py"), "w") as f:
                f.write("""
from .module import ExposedClass, exposed_func
__all__ = ["exposed_func"]
""")
            with open(os.path.join(temp_pkg, "sub", "module.py"), "w") as f:
                f.write("""
class ExposedClass:
    pass

class UnexposedClass:
    pass

def exposed_func():
    pass

def unexposed_func():
    pass
""")

            # 2. Test star imports in subpackage sub2
            os.makedirs(os.path.join(temp_pkg, "sub2"))
            with open(os.path.join(temp_pkg, "sub2", "__init__.py"), "w") as f:
                f.write("""
from .module2 import *
__all__ = []
""")
            with open(os.path.join(temp_pkg, "sub2", "module2.py"), "w") as f:
                f.write("""
class StarClass:
    pass
""")
            
            pkg_info = analyze_package("testpkg", temp_pkg)
            
            # Retrieve submodules and classes/functions
            sub_mod = pkg_info.modules.get("testpkg.sub.module")
            self.assertIsNotNone(sub_mod)
            
            exposed_cls = next(c for c in sub_mod.classes if c.name == "ExposedClass")
            unexposed_cls = next(c for c in sub_mod.classes if c.name == "UnexposedClass")
            exposed_fn = next(f for f in sub_mod.functions if f.name == "exposed_func")
            unexposed_fn = next(f for f in sub_mod.functions if f.name == "unexposed_func")
            
            # Assert exposure flags
            self.assertFalse(exposed_cls.is_unexposed)
            self.assertTrue(unexposed_cls.is_unexposed)
            self.assertFalse(exposed_fn.is_unexposed)
            self.assertTrue(unexposed_fn.is_unexposed)
            
            # Assert missing from __all__ flags
            self.assertTrue(exposed_cls.missing_from_all)
            self.assertFalse(exposed_fn.missing_from_all)
            
            # Retrieve star imported module and class
            sub2_mod = pkg_info.modules.get("testpkg.sub2.module2")
            self.assertIsNotNone(sub2_mod)
            star_cls = next(c for c in sub2_mod.classes if c.name == "StarClass")
            
            # StarClass should be exposed (not unexposed) and missing from __all__ (since __all__ = [])
            self.assertFalse(star_cls.is_unexposed)
            self.assertTrue(star_cls.missing_from_all)
            
            # Assert rich tree output contains warning labels
            f_out = io.StringIO()
            with redirect_stdout(f_out):
                render_rich_tree(pkg_info)
            output = f_out.getvalue()
            
            self.assertIn("UnexposedClass ⚠️  (unexposed)", output)
            self.assertIn("unexposed_func() ⚠️  (unexposed)", output)
            self.assertIn("ExposedClass ⚠️  (missing from __all__)", output)
            self.assertIn("StarClass ⚠️  (missing from __all__)", output)
            
        finally:
            shutil.rmtree(temp_pkg, ignore_errors=True)

if __name__ == "__main__":
    unittest.main()
