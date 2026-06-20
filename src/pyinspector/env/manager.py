import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Dict

@contextmanager
def temp_env(package_spec: str, python_version: str = None, no_build_isolation: bool = False) -> Dict[str, str]:
    """
    Context manager that:
    1. Creates a temporary directory.
    2. Initializes a uv venv.
    3. Installs the target package.
    4. Runs the locate_helper.py script inside the venv to find the installed module path(s).
    5. Yields a dictionary mapping module name to absolute file system path.
    6. Cleans up the temporary directory.
    """
    pkg_path = Path(package_spec)
    # Check for existing local .venv first to reuse it
    if pkg_path.is_dir():
        local_venv = pkg_path / ".venv"
        python_exe = local_venv / "bin" / "python"
        if not python_exe.exists():
            python_exe = local_venv / "Scripts" / "python.exe"
            
        if python_exe.exists():
            helper_path = Path(__file__).parent / "locate_helper.py"
            with open(helper_path, "r", encoding="utf-8") as f:
                helper_code = f.read()
                
            clean_env = os.environ.copy()
            clean_env.pop("VIRTUAL_ENV", None)
            clean_env.pop("PYTHONHOME", None)
            clean_env.pop("CONDA_PREFIX", None)
            
            res = subprocess.run(
                [str(python_exe), "-c", helper_code, str(pkg_path.resolve())],
                cwd=str(pkg_path),
                capture_output=True,
                text=True,
                check=True,
                env=clean_env
            )
            modules_paths = {}
            for line in res.stdout.strip().splitlines():
                if ":" in line:
                    mod, path = line.split(":", 1)
                    modules_paths[mod] = path
            yield modules_paths
            return

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
        if no_build_isolation:
            venv_cmd.append("--system-site-packages")
        
        res_venv = subprocess.run(venv_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_venv.returncode != 0:
            raise RuntimeError(f"Failed to initialize virtualenv:\n{res_venv.stderr.strip()}")
        
        # Determine path to python executable
        temp_dir_path = Path(temp_dir)
        python_exe = temp_dir_path / ".venv" / "bin" / "python"
        if not python_exe.exists():
            python_exe = temp_dir_path / ".venv" / "Scripts" / "python.exe"
            
        if not python_exe.exists():
            raise FileNotFoundError(f"Python executable not found in virtual environment at {temp_dir}")
            
        # 2. Install the package
        pkg_spec_str = str(pkg_path.resolve()) if pkg_path.exists() else package_spec
            
        install_cmd = ["uv", "pip", "install", "--python", str(python_exe), "--no-deps"]
        if no_build_isolation:
            install_cmd.append("--no-build-isolation")
        install_cmd.append(pkg_spec_str)
        
        res_install = subprocess.run(install_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_install.returncode != 0:
            raise RuntimeError(f"Installation failed:\n{res_install.stderr.strip()}")
        
        # 3. Read the helper code from locate_helper.py dynamically
        helper_path = Path(__file__).parent / "locate_helper.py"
        with open(helper_path, "r", encoding="utf-8") as f:
            helper_code = f.read()
            
        # Run helper script in venv
        res = subprocess.run(
            [str(python_exe), "-c", helper_code, pkg_spec_str],
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
