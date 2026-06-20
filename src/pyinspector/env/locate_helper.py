import importlib.metadata
import importlib.util
import sys
from pathlib import Path

def is_std_library_module(mod_name, path_abs, package_spec):
    if hasattr(sys, "stdlib_module_names") and mod_name in sys.stdlib_module_names:
        import sysconfig
        purelib = Path(sysconfig.get_path('purelib')).resolve()
        platlib = Path(sysconfig.get_path('platlib')).resolve()
        path_p = Path(path_abs).resolve()
        in_site_packages = path_p.is_relative_to(purelib) or path_p.is_relative_to(platlib)
        
        in_local_spec = False
        pkg_spec_path = Path(package_spec)
        if pkg_spec_path.exists():
            in_local_spec = path_p.is_relative_to(pkg_spec_path.resolve())
            
        if not (in_site_packages or in_local_spec):
            return True
    return False

def main():
    package_spec_str = sys.argv[1]
    package_spec = Path(package_spec_str)

    # Try to find the package name
    target_name = package_spec_str
    if package_spec.exists():
        target_name = package_spec.name

    # Normalize package name (PyPI names use hyphens, Python imports use underscores)
    clean_name = target_name.split("==")[0].split(">=")[0].split("<=")[0].strip()

    # 1. Set up sys.path and collect local modules for local checkouts
    local_modules = []
    if package_spec.is_dir():
        package_spec_resolved = package_spec.resolve()
        package_spec_resolved_str = str(package_spec_resolved)
        # If the directory itself contains __init__.py, it is the package
        if (package_spec_resolved / "__init__.py").exists():
            parent_dir = str(package_spec_resolved.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            local_modules.append(clean_name)
        else:
            if package_spec_resolved_str not in sys.path:
                sys.path.insert(0, package_spec_resolved_str)
            src_dir = package_spec_resolved / "src"
            src_dir_str = str(src_dir)
            if src_dir.is_dir() and src_dir_str not in sys.path:
                sys.path.insert(0, src_dir_str)

        # Scan root of package_spec for subdirectories with __init__.py or standalone python modules
        try:
            for entry in package_spec.iterdir():
                if entry.is_dir():
                    if entry.name != ".venv" and not entry.name.startswith(".") and (entry / "__init__.py").exists():
                        local_modules.append(entry.name)
                elif entry.is_file() and entry.suffix == ".py":
                    base = entry.stem
                    if base not in ("setup", "conftest", "noxfile", "tox", "tasks", "test", "tests"):
                        local_modules.append(base)
        except Exception:
            pass

        # Scan src/ of package_spec for package subdirectories
        src_dir = package_spec / "src"
        if src_dir.is_dir():
            try:
                for entry in src_dir.iterdir():
                    if entry.is_dir():
                        if not entry.name.startswith(".") and (entry / "__init__.py").exists():
                            local_modules.append(entry.name)
            except Exception:
                pass
    elif package_spec.is_file() and package_spec.suffix == ".py":
        parent = str(package_spec.resolve().parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        base = package_spec.stem
        local_modules.append(base)

    dists = list(importlib.metadata.distributions())
    dist = None

    # 2. Match by name case-insensitively
    for d in dists:
        name = d.metadata['Name']
        if name and name.lower() == clean_name.lower().replace('_', '-'):
            dist = d
            break

    # 3. Match by path (for local installs)
    if not dist and package_spec.exists():
        for d in dists:
            name = d.metadata['Name']
            if name and name.lower() == clean_name.lower().replace('-', '_'):
                dist = d
                break

    # 4. If still not found, search for any user-installed distribution
    if not dist:
        standard_libs = {'pip', 'setuptools', 'wheel', 'uv', 'hatchling'}
        user_dists = [d for d in dists if d.metadata['Name'] and d.metadata['Name'].lower() not in standard_libs]
        if len(user_dists) == 1:
            dist = user_dists[0]

    modules = []
    if dist:
        top_levels = dist.read_text('top_level.txt')
        if top_levels:
            modules = [line.strip() for line in top_levels.strip().splitlines() if line.strip()]
        else:
            if dist.files:
                for file in dist.files:
                    parts = file.parts
                    if len(parts) > 1 and parts[0] not in ('..', 'dist-info', '__pycache__'):
                        modules.append(parts[0])
        modules.append(dist.metadata['Name'])
    else:
        if local_modules:
            modules.extend(local_modules)
        # Only append clean_name if it is not a local directory,
        # or if it exists as an actual module/folder inside package_spec
        if not package_spec.exists():
            modules.append(clean_name)
        else:
            is_valid_local = (
                (package_spec / clean_name).exists() or
                (package_spec / f"{clean_name}.py").exists() or
                (package_spec / "__init__.py").exists()
            )
            if is_valid_local:
                modules.append(clean_name)

    modules = list(set(modules))

    results = []
    for mod_name in modules:
        mod_import_name = mod_name.replace('-', '_')
        try:
            spec = importlib.util.find_spec(mod_import_name)
            if spec:
                path = spec.submodule_search_locations[0] if spec.submodule_search_locations else spec.origin
                if path:
                    path_abs = str(Path(path).resolve())
                    if not is_std_library_module(mod_import_name, path_abs, package_spec_str):
                        results.append((mod_import_name, path_abs))
        except Exception:
            pass

    if not results:
        try:
            fallback_name = clean_name.replace('-', '_')
            spec = importlib.util.find_spec(fallback_name)
            if spec:
                path = spec.submodule_search_locations[0] if spec.submodule_search_locations else spec.origin
                if path:
                    path_abs = str(Path(path).resolve())
                    if not is_std_library_module(fallback_name, path_abs, package_spec_str):
                        results.append((fallback_name, path_abs))
        except Exception:
            pass

    for mod, path in results:
        print(f"{mod}:{path}")

if __name__ == '__main__':
    main()
