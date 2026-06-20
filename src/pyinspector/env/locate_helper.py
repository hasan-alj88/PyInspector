import importlib.metadata
import importlib.util
import sys
import os

def main():
    package_spec = sys.argv[1]

    # Try to find the package name
    target_name = package_spec
    if os.path.exists(package_spec):
        target_name = os.path.basename(os.path.normpath(package_spec))

    # Normalize package name (PyPI names use hyphens, Python imports use underscores)
    clean_name = target_name.split("==")[0].split(">=")[0].split("<=")[0].strip()

    # 1. Set up sys.path and collect local modules for local checkouts
    local_modules = []
    if os.path.isdir(package_spec):
        if package_spec not in sys.path:
            sys.path.insert(0, package_spec)
        src_dir = os.path.join(package_spec, "src")
        if os.path.isdir(src_dir) and src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        # Scan root of package_spec for subdirectories with __init__.py or standalone python modules
        try:
            for entry in os.listdir(package_spec):
                entry_path = os.path.join(package_spec, entry)
                if os.path.isdir(entry_path):
                    if entry != ".venv" and not entry.startswith(".") and os.path.exists(os.path.join(entry_path, "__init__.py")):
                        local_modules.append(entry)
                elif os.path.isfile(entry_path) and entry.endswith(".py"):
                    base = entry[:-3]
                    if base not in ("setup", "conftest", "noxfile", "tox", "tasks", "test", "tests"):
                        local_modules.append(base)
        except Exception:
            pass

        # Scan src/ of package_spec for package subdirectories
        if os.path.isdir(src_dir):
            try:
                for entry in os.listdir(src_dir):
                    entry_path = os.path.join(src_dir, entry)
                    if os.path.isdir(entry_path):
                        if not entry.startswith(".") and os.path.exists(os.path.join(entry_path, "__init__.py")):
                            local_modules.append(entry)
            except Exception:
                pass
    elif os.path.isfile(package_spec) and package_spec.endswith(".py"):
        parent = os.path.dirname(os.path.abspath(package_spec))
        if parent not in sys.path:
            sys.path.insert(0, parent)
        base = os.path.basename(package_spec)[:-3]
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
    if not dist and os.path.exists(package_spec):
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
                    results.append((mod_import_name, os.path.abspath(path)))
        except Exception:
            pass

    if not results:
        try:
            spec = importlib.util.find_spec(clean_name.replace('-', '_'))
            if spec:
                path = spec.submodule_search_locations[0] if spec.submodule_search_locations else spec.origin
                if path:
                    results.append((clean_name.replace('-', '_'), os.path.abspath(path)))
        except Exception:
            pass

    for mod, path in results:
        print(f"{mod}:{path}")

if __name__ == '__main__':
    main()
