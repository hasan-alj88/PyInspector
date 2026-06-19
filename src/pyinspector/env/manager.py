import os
import sys
import subprocess
import tempfile
import shutil
from contextlib import contextmanager
from typing import Dict

@contextmanager
def temp_env(package_spec: str, python_version: str = None) -> Dict[str, str]:
    """
    Context manager that:
    1. Creates a temporary directory.
    2. Initializes a uv venv.
    3. Installs the target package.
    4. Runs the locate_helper.py script inside the venv to find the installed module path(s).
    5. Yields a dictionary mapping module name to absolute file system path.
    6. Cleans up the temporary directory.
    """
    temp_dir = tempfile.mkdtemp(prefix="pyinspector-")
    try:
        # Prepare environment without VIRTUAL_ENV to avoid hijacking by parent venv
        clean_env = os.environ.copy()
        clean_env.pop("VIRTUAL_ENV", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env.pop("CONDA_PREFIX", None)

        # 1. Initialize uv venv
        venv_cmd = ["uv", "venv"]
        if python_version:
            venv_cmd.extend(["--python", python_version])
        
        res_venv = subprocess.run(venv_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_venv.returncode != 0:
            raise RuntimeError(f"Failed to initialize virtualenv:\n{res_venv.stderr.strip()}")
        
        # Determine path to python executable
        python_exe = os.path.join(temp_dir, ".venv", "bin", "python")
        if not os.path.exists(python_exe):
            python_exe = os.path.join(temp_dir, ".venv", "Scripts", "python.exe")
            
        if not os.path.exists(python_exe):
            raise FileNotFoundError(f"Python executable not found in virtual environment at {temp_dir}")
            
        # 2. Install the package
        if os.path.exists(package_spec):
            package_spec = os.path.abspath(package_spec)
            
        install_cmd = ["uv", "pip", "install", "--python", python_exe, "--no-deps", package_spec]
        res_install = subprocess.run(install_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_install.returncode != 0:
            raise RuntimeError(f"Installation failed:\n{res_install.stderr.strip()}")
        
        # 3. Read the helper code from locate_helper.py dynamically
        helper_path = os.path.join(os.path.dirname(__file__), "locate_helper.py")
        with open(helper_path, "r", encoding="utf-8") as f:
            helper_code = f.read()
            
        # Run helper script in venv
        res = subprocess.run(
            [python_exe, "-c", helper_code, package_spec],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
            env=clean_env
        )
        
        # Parse results
        modules_paths = {}
        for line in res.stdout.strip().splitlines():
            if ":" in line:
                mod, path = line.split(":", 1)
                modules_paths[mod] = path
                
        yield modules_paths
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
