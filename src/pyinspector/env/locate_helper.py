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

    dists = list(importlib.metadata.distributions())
    dist = None

    # 1. Match by name case-insensitively
    for d in dists:
        name = d.metadata['Name']
        if name and name.lower() == clean_name.lower().replace('_', '-'):
            dist = d
            break

    # 2. Match by path (for local installs)
    if not dist and os.path.exists(package_spec):
        for d in dists:
            name = d.metadata['Name']
            if name and name.lower() == clean_name.lower().replace('-', '_'):
                dist = d
                break

    # If still not found, search for any user-installed distribution
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
