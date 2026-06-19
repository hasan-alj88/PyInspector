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

if __name__ == "__main__":
    unittest.main()
