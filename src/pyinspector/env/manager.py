import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from contextlib import contextmanager
from typing import Dict, List, Optional

class EnvResult(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.version: Optional[str] = None
        self.summary: Optional[str] = None
        self.homepage: Optional[str] = None
        self.author: Optional[str] = None
        self.dependencies: List[str] = []
        self.dependency_tree: Optional[str] = None

def get_package_name_from_spec(package_spec: str) -> str:
    p = Path(package_spec)
    if p.exists():
        pyproject = p / "pyproject.toml"
        if pyproject.is_file():
            try:
                with open(pyproject, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip().startswith("name ="):
                            parts = line.split("=", 1)
                            return parts[1].strip().strip('"').strip("'")
            except Exception:
                pass
        return p.resolve().name
    
    name = package_spec.split("[")[0]
    for op in ("==", ">=", "<=", "<", ">", "~=", "!=", ";"):
        if op in name:
            name = name.split(op)[0]
    return name.strip()

def fetch_env_metadata(python_exe: Path, package_spec: str, clean_env: dict, cwd: str, modules_paths: dict) -> EnvResult:
    res_dict = EnvResult(modules_paths)
    pkg_name = get_package_name_from_spec(package_spec)
    
    # 1. Run uv pip check
    check_cmd = ["uv", "pip", "check", "--python", str(python_exe)]
    res_check = subprocess.run(check_cmd, cwd=cwd, capture_output=True, text=True, env=clean_env)
    if res_check.returncode != 0:
        msg = res_check.stdout.strip() or res_check.stderr.strip()
        print(f"⚠️  Dependency conflicts detected:\n{msg}", file=sys.stderr)
        
    # 2. Run uv pip show
    show_cmd = ["uv", "pip", "show", pkg_name, "--python", str(python_exe)]
    res_show = subprocess.run(show_cmd, cwd=cwd, capture_output=True, text=True, env=clean_env)
    if res_show.returncode == 0:
        for line in res_show.stdout.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k == "version":
                    res_dict.version = v
                elif k == "summary":
                    res_dict.summary = v
                elif k == "home-page":
                    res_dict.homepage = v
                elif k == "author":
                    res_dict.author = v
                elif k == "requires":
                    res_dict.dependencies = [r.strip() for r in v.split(",") if r.strip()]
                    
    # 3. Run uv tree
    tree_cmd = ["uv", "tree", "--python", str(python_exe), "--package", pkg_name]
    res_tree = subprocess.run(tree_cmd, cwd=cwd, capture_output=True, text=True, env=clean_env)
    if res_tree.returncode == 0 and res_tree.stdout.strip():
        res_dict.dependency_tree = res_tree.stdout
    else:
        tree_cmd_fallback = ["uv", "tree", "--python", str(python_exe)]
        res_tree_fallback = subprocess.run(tree_cmd_fallback, cwd=cwd, capture_output=True, text=True, env=clean_env)
        if res_tree_fallback.returncode == 0:
            res_dict.dependency_tree = res_tree_fallback.stdout
            
    return res_dict

@contextmanager
def temp_env(package_spec: str, python_version: str = None, no_build_isolation: bool = False) -> EnvResult:
    """
    Context manager that:
    1. Creates a temporary directory.
    2. Initializes a uv venv.
    3. Installs the target package.
    4. Runs the locate_helper.py script inside the venv to find the installed module path(s).
    5. Yields a dictionary mapping module name to absolute file system path, enriched with metadata.
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
                    
            yield fetch_env_metadata(python_exe, package_spec, clean_env, str(pkg_path), modules_paths)
            return

    temp_dir = tempfile.mkdtemp(prefix="pyinspector-")
    try:
        clean_env = os.environ.copy()
        clean_env.pop("VIRTUAL_ENV", None)
        clean_env.pop("PYTHONHOME", None)
        clean_env.pop("CONDA_PREFIX", None)

        venv_cmd = ["uv", "venv"]
        if python_version:
            venv_cmd.extend(["--python", python_version])
        if no_build_isolation:
            venv_cmd.append("--system-site-packages")
        
        res_venv = subprocess.run(venv_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_venv.returncode != 0:
            raise RuntimeError(f"Failed to initialize virtualenv:\n{res_venv.stderr.strip()}")
        
        temp_dir_path = Path(temp_dir)
        python_exe = temp_dir_path / ".venv" / "bin" / "python"
        if not python_exe.exists():
            python_exe = temp_dir_path / ".venv" / "Scripts" / "python.exe"
            
        if not python_exe.exists():
            raise FileNotFoundError(f"Python executable not found in virtual environment at {temp_dir}")
            
        pkg_spec_str = str(pkg_path.resolve()) if pkg_path.exists() else package_spec
            
        install_cmd = ["uv", "pip", "install", "--python", str(python_exe), "--no-deps"]
        if no_build_isolation:
            install_cmd.append("--no-build-isolation")
        install_cmd.append(pkg_spec_str)
        
        res_install = subprocess.run(install_cmd, cwd=temp_dir, capture_output=True, text=True, env=clean_env)
        if res_install.returncode != 0:
            raise RuntimeError(f"Installation failed:\n{res_install.stderr.strip()}")
            
        # Write dummy pyproject.toml inside temp_dir to enable uv tree
        try:
            dependency_str = Path(pkg_spec_str).as_posix() if pkg_path.exists() else package_spec
            with open(Path(temp_dir) / "pyproject.toml", "w", encoding="utf-8") as f:
                f.write(f"""
[project]
name = "dummy"
version = "0.1.0"
dependencies = [
    "{dependency_str}"
]
""")
        except Exception:
            pass
        
        helper_path = Path(__file__).parent / "locate_helper.py"
        with open(helper_path, "r", encoding="utf-8") as f:
            helper_code = f.read()
            
        res = subprocess.run(
            [str(python_exe), "-c", helper_code, pkg_spec_str],
            cwd=temp_dir,
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
                
        yield fetch_env_metadata(python_exe, package_spec, clean_env, temp_dir, modules_paths)
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
