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

if __name__ == "__main__":
    unittest.main()
