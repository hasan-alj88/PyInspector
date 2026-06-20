import os
import sys
import click
from rich.console import Console
from rich.table import Table
from ..env import temp_env
from ..analyzer import analyze_package, build_oop_graph
from ..viewer import (
    render_rich_tree,
    export_json,
    export_yaml,
    render_oop_tree,
    render_oop_mermaid,
    render_oop_table
)
from ..comparer import compare_packages, render_comparison

console = Console()

@click.group()
def cli():
    """PyInspector: Statically inspect python packages inside isolated environments."""
    pass

@cli.command()
@click.argument("package_spec")
@click.option("--python", default=None, help="Python version to use (e.g., 3.10).")
@click.option("--version", default=None, help="Version of the package to install.")
@click.option("--format", type=click.Choice(["tree", "json", "yaml"]), default="tree", help="Output format.")
@click.option("--output", default=None, help="Save output to this file path.")
@click.option("--private", is_flag=True, help="Include private and protected members (starting with '_').")
@click.option("--depth", type=int, default=None, help="Limit tree rendering depth.")
@click.option("--no-build-isolation", is_flag=True, help="Disable build isolation when installing local packages.")
def inspect(package_spec, python, version, format, output, private, depth, no_build_isolation):
    """
    Inspect the API structure of a package.
    
    PACKAGE_SPEC can be a PyPI package name (e.g. 'requests'), a version spec
    (e.g. 'requests==2.31.0'), or a path to a local directory or package.
    """
    if version:
        if "==" in package_spec or ">=" in package_spec or "<=" in package_spec:
            console.print("[yellow]Warning: Overriding version spec in package name with --version flag.[/yellow]")
            name = package_spec.split("=")[0].split(">")[0].split("<")[0].strip()
            package_spec = f"{name}=={version}"
        else:
            package_spec = f"{package_spec}=={version}"
            
    try:
        with console.status(f"[bold green]Setting up environment and installing {package_spec}...[/bold green]"):
            with temp_env(package_spec, python_version=python, no_build_isolation=no_build_isolation) as modules:
                if not modules:
                    console.print(f"[bold red]Error: No modules could be resolved for package spec '{package_spec}'.[/bold red]")
                    sys.exit(1)
                
                keys = list(modules.keys())
                primary_mod = keys[0]
                name_clean = package_spec.split("=")[0].split(">")[0].split("<")[0].strip().replace("-", "_").lower()
                for k in keys:
                    if k.lower() == name_clean:
                        primary_mod = k
                        break
                        
                pkg_path = modules[primary_mod]
                pkg_info = analyze_package(primary_mod, pkg_path)
                
        if format == "tree":
            render_rich_tree(pkg_info, show_private=private, max_depth=depth)
        elif format == "json":
            out_str = export_json(pkg_info, show_private=private)
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(out_str)
                console.print(f"[green]Saved JSON output to {output}[/green]")
            else:
                print(out_str)
        elif format == "yaml":
            out_str = export_yaml(pkg_info, show_private=private)
            if output:
                with open(output, "w", encoding="utf-8") as f:
                    f.write(out_str)
                console.print(f"[green]Saved YAML output to {output}[/green]")
            else:
                print(out_str)
                
    except Exception as e:
        console.print(f"[bold red]Error during inspection: {e}[/bold red]")
        sys.exit(1)

@cli.command()
@click.argument("package_spec")
@click.argument("query")
@click.option("--python", default=None, help="Python version to use.")
@click.option("--private", is_flag=True, help="Include private and protected members in search.")
@click.option("--no-build-isolation", is_flag=True, help="Disable build isolation when installing local packages.")
def search(package_spec, query, python, private, no_build_isolation):
    """
    Search for a class or function inside a package.
    
    PACKAGE_SPEC can be a PyPI package or local path.
    QUERY is the term to search for in class/function/method names.
    """
    try:
        with console.status(f"[bold green]Analyzing {package_spec}...[/bold green]"):
            with temp_env(package_spec, python_version=python, no_build_isolation=no_build_isolation) as modules:
                if not modules:
                    console.print(f"[bold red]Error: No modules resolved for '{package_spec}'.[/bold red]")
                    sys.exit(1)
                
                keys = list(modules.keys())
                primary_mod = keys[0]
                name_clean = package_spec.split("=")[0].split(">")[0].split("<")[0].strip().replace("-", "_").lower()
                for k in keys:
                    if k.lower() == name_clean:
                        primary_mod = k
                        break
                        
                pkg_path = modules[primary_mod]
                pkg_info = analyze_package(primary_mod, pkg_path)
                
        results = []
        query_lower = query.lower()
        
        for mod_name, mod_info in pkg_info.modules.items():
            for func in mod_info.functions:
                if not private and func.name.startswith("_"):
                    continue
                if query_lower in func.name.lower():
                    results.append(("Function", f"{mod_name}.{func.name}", func.signature, func.docstring))
            
            for cls in mod_info.classes:
                if not private and cls.name.startswith("_"):
                    continue
                if query_lower in cls.name.lower():
                    results.append(("Class", f"{mod_name}.{cls.name}", cls.signature, cls.docstring))
                    
                for method in cls.methods:
                    if not private and method.name.startswith("_") and method.name != "__init__":
                        continue
                    if query_lower in method.name.lower():
                        results.append(("Method", f"{mod_name}.{cls.name}.{method.name}", method.signature, method.docstring))
                        
        if not results:
            console.print(f"[yellow]No matches found for query '{query}' in {package_spec}[/yellow]")
            return
            
        table = Table(title=f"Search Results for '{query}' in {package_spec}", show_header=True, header_style="bold green")
        table.add_column("Type", style="cyan")
        table.add_column("Full Path", style="bold white")
        table.add_column("Signature", style="dim white")
        table.add_column("Docstring Snippet", style="italic dim")
        
        for r_type, path, sig, doc in results:
            doc_snippet = ""
            if doc:
                first_line = doc.strip().splitlines()[0]
                if len(first_line) > 50:
                    first_line = first_line[:47] + "..."
                doc_snippet = first_line
            table.add_row(r_type, path, sig, doc_snippet)
            
        console.print(table)
        
    except Exception as e:
        console.print(f"[bold red]Error during search: {e}[/bold red]")
        sys.exit(1)

@cli.command()
@click.argument("package_name")
@click.argument("version_a")
@click.argument("version_b")
@click.option("--python", default=None, help="Python version to use.")
@click.option("--no-build-isolation", is_flag=True, help="Disable build isolation when installing local packages.")
def compare(package_name, version_a, version_b, python, no_build_isolation):
    """
    Compare the API structure of two versions of a package.
    
    PACKAGE_NAME: PyPI name of the package.
    VERSION_A: Version string (e.g. 2.31.0) or path to local package version.
    VERSION_B: Version string (e.g. 2.32.3) or path to local package version.
    """
    def construct_spec(name, ver):
        if os.path.exists(ver):
            return ver
        return f"{name}=={ver}"
        
    spec_a = construct_spec(package_name, version_a)
    spec_b = construct_spec(package_name, version_b)
    
    pkg_info_a = None
    pkg_info_b = None
    
    try:
        with console.status(f"[bold green]Analyzing Version A ({spec_a})...[/bold green]"):
            with temp_env(spec_a, python_version=python, no_build_isolation=no_build_isolation) as modules_a:
                if not modules_a:
                    console.print(f"[bold red]Error: No modules resolved for Version A '{spec_a}'.[/bold red]")
                    sys.exit(1)
                keys = list(modules_a.keys())
                primary_mod = keys[0]
                name_clean = package_name.replace("-", "_").lower()
                for k in keys:
                    if k.lower() == name_clean:
                        primary_mod = k
                        break
                pkg_info_a = analyze_package(primary_mod, modules_a[primary_mod])
                
        with console.status(f"[bold green]Analyzing Version B ({spec_b})...[/bold green]"):
            with temp_env(spec_b, python_version=python, no_build_isolation=no_build_isolation) as modules_b:
                if not modules_b:
                    console.print(f"[bold red]Error: No modules resolved for Version B '{spec_b}'.[/bold red]")
                    sys.exit(1)
                keys = list(modules_b.keys())
                primary_mod = keys[0]
                name_clean = package_name.replace("-", "_").lower()
                for k in keys:
                    if k.lower() == name_clean:
                        primary_mod = k
                        break
                pkg_info_b = analyze_package(primary_mod, modules_b[primary_mod])
                
        diff = compare_packages(pkg_info_a, pkg_info_b, version_a, version_b)
        render_comparison(diff)
        
    except Exception as e:
        console.print(f"[bold red]Error during version comparison: {e}[/bold red]")
        sys.exit(1)

@cli.command()
@click.argument("package_spec")
@click.option("--python", default=None, help="Python version to use (e.g., 3.10).")
@click.option("--format", type=click.Choice(["tree", "mermaid", "table"]), default="tree", help="Visual format of OOP relationships.")
@click.option("--include-external", is_flag=True, help="Include external parent classes.")
@click.option("--no-composition", is_flag=True, help="Disable composition analysis.")
@click.option("--no-build-isolation", is_flag=True, help="Disable build isolation when installing local packages.")
def oop(package_spec, python, format, include_external, no_composition, no_build_isolation):
    """
    Map the OOP UML relationships (inheritance & composition) of a package.
    
    This command models classes starting from the root 'object' and shows
    subclasses as tree nodes and composition as sub-elements.
    """
    try:
        with console.status(f"[bold green]Setting up environment and analyzing {package_spec}...[/bold green]"):
            with temp_env(package_spec, python_version=python, no_build_isolation=no_build_isolation) as modules:
                if not modules:
                    console.print(f"[bold red]Error: No modules could be resolved for package spec '{package_spec}'.[/bold red]")
                    sys.exit(1)
                
                keys = list(modules.keys())
                primary_mod = keys[0]
                name_clean = package_spec.split("=")[0].split(">")[0].split("<")[0].strip().replace("-", "_").lower()
                for k in keys:
                    if k.lower() == name_clean:
                        primary_mod = k
                        break
                        
                pkg_path = modules[primary_mod]
                pkg_info = analyze_package(primary_mod, pkg_path)
                
        # Build OOP graph
        root_node = build_oop_graph(pkg_info, include_external=include_external)
        
        # Render output
        show_composition = not no_composition
        if format == "tree":
            render_oop_tree(root_node, show_composition=show_composition)
        elif format == "mermaid":
            mermaid_str = render_oop_mermaid(root_node, show_composition=show_composition)
            print(mermaid_str)
        elif format == "table":
            render_oop_table(root_node, show_composition=show_composition)
            
    except Exception as e:
        console.print(f"[bold red]Error during OOP analysis: {e}[/bold red]")
        sys.exit(1)
