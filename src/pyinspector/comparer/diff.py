import os
import sys
import tomllib
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from ..analyzer import PackageInfo

@dataclass
class DiffResult:
    package_name: str
    version_a: str
    version_b: str
    requires_python_a: Optional[str] = None
    requires_python_b: Optional[str] = None
    
    # Modules level
    added_modules: List[str] = field(default_factory=list)
    removed_modules: List[str] = field(default_factory=list)
    
    # Classes level (module.ClassName)
    added_classes: List[str] = field(default_factory=list)
    removed_classes: List[str] = field(default_factory=list)
    
    # Functions level (module.function_name)
    added_functions: List[str] = field(default_factory=list)
    removed_functions: List[str] = field(default_factory=list)
    # Mapping of name to (sig_a, sig_b)
    modified_functions: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    
    # Methods level (module.ClassName.method_name)
    added_methods: List[str] = field(default_factory=list)
    removed_methods: List[str] = field(default_factory=list)
    modified_methods: Dict[str, Tuple[str, str]] = field(default_factory=dict)
    
    # Dependencies level
    added_dependencies: List[str] = field(default_factory=list)
    removed_dependencies: List[str] = field(default_factory=list)

def get_local_requires_python(path: str) -> Optional[str]:
    """Statically reads requires-python from pyproject.toml if path is a local folder."""
    if not os.path.isdir(path):
        return None
    pyproject_path = os.path.join(path, "pyproject.toml")
    if os.path.exists(pyproject_path):
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                return data.get("project", {}).get("requires-python")
        except Exception:
            pass
    return None

def fetch_pypi_requires_python(package_name: str, version: str) -> Optional[str]:
    """Fetches requires-python metadata from PyPI JSON API for a specific version."""
    url = f"https://pypi.org/pypi/{package_name}/{version}/json"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("info", {}).get("requires_python")
    except Exception:
        pass
    return None

def compare_packages(pkg_a: PackageInfo, pkg_b: PackageInfo, version_a: str, version_b: str) -> DiffResult:
    """Compares two PackageInfo structures and generates a detailed API DiffResult."""
    diff = DiffResult(package_name=pkg_a.name, version_a=version_a, version_b=version_b)
    
    # Resolve requires-python
    if os.path.exists(version_a):
        diff.requires_python_a = get_local_requires_python(version_a)
    else:
        diff.requires_python_a = fetch_pypi_requires_python(pkg_a.name, version_a)
        
    if os.path.exists(version_b):
        diff.requires_python_b = get_local_requires_python(version_b)
    else:
        diff.requires_python_b = fetch_pypi_requires_python(pkg_b.name, version_b)
        
    # Compare modules
    mods_a = set(pkg_a.modules.keys())
    mods_b = set(pkg_b.modules.keys())
    
    diff.added_modules = sorted(list(mods_b - mods_a))
    diff.removed_modules = sorted(list(mods_a - mods_b))
    
    common_mods = mods_a & mods_b
    
    for mod_name in common_mods:
        mod_a = pkg_a.modules[mod_name]
        mod_b = pkg_b.modules[mod_name]
        
        # Compare functions
        funcs_a = {f.name: f for f in mod_a.functions}
        funcs_b = {f.name: f for f in mod_b.functions}
        
        funcs_a_keys = set(funcs_a.keys())
        funcs_b_keys = set(funcs_b.keys())
        
        for f_name in (funcs_b_keys - funcs_a_keys):
            diff.added_functions.append(f"{mod_name}.{f_name}")
        for f_name in (funcs_a_keys - funcs_b_keys):
            diff.removed_functions.append(f"{mod_name}.{f_name}")
            
        for f_name in (funcs_a_keys & funcs_b_keys):
            sig_a = funcs_a[f_name].signature
            sig_b = funcs_b[f_name].signature
            if sig_a != sig_b:
                diff.modified_functions[f"{mod_name}.{f_name}"] = (sig_a, sig_b)
                
        # Compare classes
        classes_a = {c.name: c for c in mod_a.classes}
        classes_b = {c.name: c for c in mod_b.classes}
        
        classes_a_keys = set(classes_a.keys())
        classes_b_keys = set(classes_b.keys())
        
        for c_name in (classes_b_keys - classes_a_keys):
            diff.added_classes.append(f"{mod_name}.{c_name}")
        for c_name in (classes_a_keys - classes_b_keys):
            diff.removed_classes.append(f"{mod_name}.{c_name}")
            
        # Compare class methods
        for c_name in (classes_a_keys & classes_b_keys):
            cls_a = classes_a[c_name]
            cls_b = classes_b[c_name]
            
            methods_a = {m.name: m for m in cls_a.methods}
            methods_b = {m.name: m for m in cls_b.methods}
            
            methods_a_keys = set(methods_a.keys())
            methods_b_keys = set(methods_b.keys())
            
            for m_name in (methods_b_keys - methods_a_keys):
                diff.added_methods.append(f"{mod_name}.{c_name}.{m_name}")
            for m_name in (methods_a_keys - methods_b_keys):
                diff.removed_methods.append(f"{mod_name}.{c_name}.{m_name}")
                
            for m_name in (methods_a_keys & methods_b_keys):
                sig_a = methods_a[m_name].signature
                sig_b = methods_b[m_name].signature
                if sig_a != sig_b:
                    diff.modified_methods[f"{mod_name}.{c_name}.{m_name}"] = (sig_a, sig_b)
                    
    # Sort elements for presentation
    diff.added_functions.sort()
    diff.removed_functions.sort()
    diff.added_classes.sort()
    diff.removed_classes.sort()
    diff.added_methods.sort()
    diff.removed_methods.sort()
    
    # Compare dependencies
    deps_a = set(pkg_a.dependencies) if pkg_a.dependencies else set()
    deps_b = set(pkg_b.dependencies) if pkg_b.dependencies else set()
    diff.added_dependencies = sorted(list(deps_b - deps_a))
    diff.removed_dependencies = sorted(list(deps_a - deps_b))
    
    return diff

def render_comparison(diff: DiffResult):
    """Prints a structured, user-friendly comparison report to the console."""
    console = Console()
    
    title = f"API Comparison: {diff.package_name}"
    subtitle = f"{diff.version_a} ➔ {diff.version_b}"
    console.print(Panel.fit(
        f"[bold yellow]{title}[/bold yellow]\n[dim white]{subtitle}[/dim white]",
        border_style="yellow"
    ))
    
    py_table = Table(title="Python Version Support Compatibility", show_header=True, header_style="bold blue")
    py_table.add_column("Version / Source", style="cyan")
    py_table.add_column("Requires Python Constraint", style="green")
    
    py_table.add_row(diff.version_a, diff.requires_python_a or "Not specified (or local without pyproject.toml)")
    py_table.add_row(diff.version_b, diff.requires_python_b or "Not specified (or local without pyproject.toml)")
    console.print(py_table)
    console.print()
    
    stats_table = Table(title="API Change Summary Statistics", show_header=True, header_style="bold magenta")
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Added", style="green")
    stats_table.add_column("Removed", style="red")
    stats_table.add_column("Modified (Signature Changed)", style="yellow")
    
    stats_table.add_row("Modules", str(len(diff.added_modules)), str(len(diff.removed_modules)), "-")
    stats_table.add_row("Classes", str(len(diff.added_classes)), str(len(diff.removed_classes)), "-")
    stats_table.add_row("Functions", str(len(diff.added_functions)), str(len(diff.removed_functions)), str(len(diff.modified_functions)))
    stats_table.add_row("Methods", str(len(diff.added_methods)), str(len(diff.removed_methods)), str(len(diff.modified_methods)))
    
    console.print(stats_table)
    console.print()
    
    details_table = Table(title="API Structural Additions & Deletions", show_header=True, header_style="bold cyan")
    details_table.add_column("Change Type", style="bold")
    details_table.add_column("Element Type", style="bold")
    details_table.add_column("Element Name/Path", style="white")
    
    has_changes = False
    for mod in diff.added_modules:
        details_table.add_row("[green]Added[/green]", "Module", mod)
        has_changes = True
    for mod in diff.removed_modules:
        details_table.add_row("[red]Removed[/red]", "Module", mod)
        has_changes = True
        
    for cls in diff.added_classes:
        details_table.add_row("[green]Added[/green]", "Class", cls)
        has_changes = True
    for cls in diff.removed_classes:
        details_table.add_row("[red]Removed[/red]", "Class", cls)
        has_changes = True
        
    for func in diff.added_functions:
        details_table.add_row("[green]Added[/green]", "Function", func)
        has_changes = True
    for func in diff.removed_functions:
        details_table.add_row("[red]Removed[/red]", "Function", func)
        has_changes = True
        
    for method in diff.added_methods:
        details_table.add_row("[green]Added[/green]", "Method", method)
        has_changes = True
    for method in diff.removed_methods:
        details_table.add_row("[red]Removed[/red]", "Method", method)
        has_changes = True
        
    if has_changes:
        console.print(details_table)
        console.print()
        
    if diff.modified_functions or diff.modified_methods:
        sig_table = Table(title="Function & Method Signature Modifications", show_header=True, header_style="bold yellow", collapse_padding=True)
        sig_table.add_column("Element", style="cyan", width=30)
        sig_table.add_column(f"vA: {diff.version_a}", style="red")
        sig_table.add_column(f"vB: {diff.version_b}", style="green")
        
        for name, (sig_a, sig_b) in diff.modified_functions.items():
            sig_table.add_row(name, sig_a, sig_b)
        for name, (sig_a, sig_b) in diff.modified_methods.items():
            sig_table.add_row(name, sig_a, sig_b)
            
        console.print(sig_table)
        console.print()
    
    if not has_changes and not diff.modified_functions and not diff.modified_methods:
        console.print("[bold green]No API structural changes detected between these two versions.[/bold green]")
        
    if diff.added_dependencies or diff.removed_dependencies:
        dep_table = Table(title="Dependency Package Changes", show_header=True, header_style="bold blue")
        dep_table.add_column("Change Type", style="bold")
        dep_table.add_column("Dependency Package Name", style="white")
        for dep in diff.added_dependencies:
            dep_table.add_row("[green]Added Dependency[/green]", dep)
        for dep in diff.removed_dependencies:
            dep_table.add_row("[red]Removed Dependency[/red]", dep)
        console.print(dep_table)
        console.print()
