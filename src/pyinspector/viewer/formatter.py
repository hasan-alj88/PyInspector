import json
import yaml
from typing import Optional, Dict, Any
from rich.tree import Tree
from rich.table import Table
from rich.text import Text
from rich.console import Console
from ..analyzer import PackageInfo, ModuleInfo, ClassInfo, FunctionInfo, OOPClassNode

def build_module_trie(pkg_info: PackageInfo) -> Dict[str, Any]:
    """Builds a hierarchical trie from module name dot-paths."""
    trie = {}
    for mod_name, mod_info in pkg_info.modules.items():
        parts = mod_name.split(".")
        current = trie
        for part in parts:
            if part not in current:
                current[part] = {}
            current = current[part]
        current["__module_info__"] = mod_info
    return trie

def add_trie_to_tree(
    trie_node: Dict[str, Any],
    tree_node: Tree,
    current_depth: int,
    max_depth: Optional[int],
    show_private: bool
):
    """Recursively populates a Rich Tree from a module trie."""
    if max_depth is not None and current_depth > max_depth:
        return
        
    for key in sorted(trie_node.keys()):
        if key == "__module_info__":
            continue
            
        sub_trie = trie_node[key]
        mod_info: Optional[ModuleInfo] = sub_trie.get("__module_info__")
        
        if mod_info:
            if mod_info.is_recursive:
                label = Text(f"{key} (module -> loop/already explored: {mod_info.points_to})", style="italic dim yellow")
            else:
                label = Text(f"{key}", style="bold blue")
        else:
            label = Text(f"{key}", style="dim blue")
            
        branch = tree_node.add(label)
        
        if mod_info and mod_info.is_recursive:
            continue
        
        if mod_info:
            # Render Classes
            for cls in mod_info.classes:
                if not show_private and cls.name.startswith("_"):
                    continue
                    
                cls_label = Text("class ", style="bold magenta")
                cls_label.append(cls.name, style="bold cyan")
                
                sig_suffix = cls.signature
                if sig_suffix.startswith(f"class {cls.name}"):
                    sig_suffix = sig_suffix[len(f"class {cls.name}"):]
                cls_label.append(sig_suffix, style="italic dim white")
                
                cls_branch = branch.add(cls_label)
                
                # Render Methods
                for method in cls.methods:
                    if not show_private and method.name.startswith("_") and method.name != "__init__":
                        continue
                        
                    method_label = Text()
                    if method.is_async:
                        method_label.append("async ", style="bold red")
                    method_label.append("def ", style="bold green")
                    method_label.append(method.name, style="bold white")
                    
                    sig_suffix = method.signature
                    if sig_suffix.startswith("def "):
                        sig_suffix = sig_suffix[4:]
                    elif sig_suffix.startswith("async def "):
                        sig_suffix = sig_suffix[10:]
                    if sig_suffix.startswith(method.name):
                        sig_suffix = sig_suffix[len(method.name):]
                        
                    method_label.append(sig_suffix, style="dim white")
                    cls_branch.add(method_label)
                    
            # Render Functions
            for func in mod_info.functions:
                if not show_private and func.name.startswith("_"):
                    continue
                    
                func_label = Text()
                if func.is_async:
                    func_label.append("async ", style="bold red")
                func_label.append("def ", style="bold green")
                func_label.append(func.name, style="bold white")
                
                sig_suffix = func.signature
                if sig_suffix.startswith("def "):
                    sig_suffix = sig_suffix[4:]
                elif sig_suffix.startswith("async def "):
                    sig_suffix = sig_suffix[10:]
                if sig_suffix.startswith(func.name):
                    sig_suffix = sig_suffix[len(func.name):]
                    
                func_label.append(sig_suffix, style="dim white")
                branch.add(func_label)
                
        add_trie_to_tree(sub_trie, branch, current_depth + 1, max_depth, show_private)

def render_rich_tree(pkg_info: PackageInfo, show_private: bool = False, max_depth: Optional[int] = None):
    """Prints a beautiful colored tree of the package API using Rich."""
    console = Console()
    
    trie = build_module_trie(pkg_info)
    
    root_label = Text(f"📦 {pkg_info.name}", style="bold yellow")
    root_label.append(f" ({pkg_info.path})", style="dim white")
    
    tree = Tree(root_label)
    add_trie_to_tree(trie, tree, 1, max_depth, show_private)
    
    console.print(tree)

def package_to_dict(pkg_info: PackageInfo, show_private: bool) -> Dict[str, Any]:
    """Converts PackageInfo to a clean dict for export."""
    data = {
        "package": pkg_info.name,
        "path": pkg_info.path,
        "modules": {}
    }
    
    for mod_name, mod_info in pkg_info.modules.items():
        mod_data = {
            "relative_path": mod_info.relative_path,
            "is_recursive": mod_info.is_recursive,
            "points_to": mod_info.points_to,
            "classes": [],
            "functions": []
        }
        
        if mod_info.is_recursive:
            data["modules"][mod_name] = mod_data
            continue
            
        for cls in mod_info.classes:
            if not show_private and cls.name.startswith("_"):
                continue
            cls_data = {
                "name": cls.name,
                "signature": cls.signature,
                "docstring": cls.docstring,
                "methods": []
            }
            for method in cls.methods:
                if not show_private and method.name.startswith("_") and method.name != "__init__":
                    continue
                cls_data["methods"].append({
                    "name": method.name,
                    "signature": method.signature,
                    "docstring": method.docstring,
                    "is_async": method.is_async
                })
            mod_data["classes"].append(cls_data)
            
        for func in mod_info.functions:
            if not show_private and func.name.startswith("_"):
                continue
            mod_data["functions"].append({
                "name": func.name,
                "signature": func.signature,
                "docstring": func.docstring,
                "is_async": func.is_async
            })
            
        data["modules"][mod_name] = mod_data
    return data

def export_json(pkg_info: PackageInfo, show_private: bool = False) -> str:
    """Returns JSON representation of the package API."""
    data = package_to_dict(pkg_info, show_private)
    return json.dumps(data, indent=2)

def export_yaml(pkg_info: PackageInfo, show_private: bool = False) -> str:
    """Returns YAML representation of the package API."""
    data = package_to_dict(pkg_info, show_private)
    return yaml.dump(data, sort_keys=False)

def render_oop_tree(root_node: OOPClassNode, show_composition: bool = True):
    """Prints a beautiful colored ASCII tree of class inheritance and composition."""
    console = Console()
    
    root_label = Text("Root ", style="dim white")
    root_label.append(root_node.name, style="bold yellow")
    tree = Tree(root_label)
    
    def add_node(oop_node: OOPClassNode, tree_node: Tree):
        # Sort subclasses alphabetically by name
        for sub in sorted(oop_node.subclasses, key=lambda x: x.name):
            if sub.is_external:
                label = Text("class ", style="bold magenta")
                label.append(sub.name, style="italic dim yellow")
                label.append(" (external)", style="dim white")
            else:
                label = Text("class ", style="bold magenta")
                label.append(sub.name, style="bold cyan")
                
            branch = tree_node.add(label)
            
            # Add composition nodes if requested and present
            if show_composition:
                # Resolved composition
                for attr in sorted(sub.resolved_composition.keys()):
                    comp = sub.resolved_composition[attr]
                    comp_label = Text("✦ composes ", style="dim green")
                    comp_label.append(comp.name, style="bold cyan")
                    comp_label.append(f" (as {attr})", style="dim white")
                    branch.add(comp_label)
                # External composition
                for attr in sorted(sub.external_composition.keys()):
                    ext_type = sub.external_composition[attr]
                    clean_ext = ext_type.split(".")[-1]
                    comp_label = Text("✦ composes ", style="dim green")
                    comp_label.append(clean_ext, style="italic dim yellow")
                    comp_label.append(f" (as {attr}, external)", style="dim white")
                    branch.add(comp_label)
            
            # Recurse
            add_node(sub, branch)
            
    add_node(root_node, tree)
    console.print(tree)

def render_oop_mermaid(root_node: OOPClassNode, show_composition: bool = True) -> str:
    """Generates a Mermaid Class Diagram representing inheritance and composition."""
    inheritance_lines = []
    composition_lines = []
    visited = set()
    
    def collect_relations(node: OOPClassNode):
        if node.name in visited:
            return
        visited.add(node.name)
        
        # Sort subclasses to ensure deterministic output
        for sub in sorted(node.subclasses, key=lambda x: x.name):
            if node.name != "object":
                inheritance_lines.append(f"    {node.name} <|-- {sub.name}")
            collect_relations(sub)
            
        if show_composition:
            for attr in sorted(node.resolved_composition.keys()):
                comp = node.resolved_composition[attr]
                composition_lines.append(f"    {node.name} *-- {comp.name} : {attr}")
            for attr in sorted(node.external_composition.keys()):
                ext_type = node.external_composition[attr]
                clean_ext = ext_type.split(".")[-1]
                composition_lines.append(f"    {node.name} *-- {clean_ext} : {attr}")
                
    collect_relations(root_node)
    
    lines = ["classDiagram"]
    # Add inheritance lines, deduplicated
    seen_inh = set()
    for line in inheritance_lines:
        if line not in seen_inh:
            lines.append(line)
            seen_inh.add(line)
            
    # Add composition lines, deduplicated
    seen_comp = set()
    for line in composition_lines:
        if line not in seen_comp:
            lines.append(line)
            seen_comp.add(line)
            
    return "\n".join(lines)

def render_oop_table(root_node: OOPClassNode, show_composition: bool = True):
    """Prints a structured tabular report of the classes and their OOP relations."""
    console = Console()
    
    table = Table(title="OOP Class Relationships Map", show_header=True, header_style="bold green")
    table.add_column("Class Name", style="bold cyan")
    table.add_column("Module Location", style="dim white")
    table.add_column("Inherits From (Bases)", style="magenta")
    if show_composition:
        table.add_column("Composes Attributes", style="green")
        
    visited = set()
    rows = []
    
    def collect_rows(node: OOPClassNode):
        if node.name in visited:
            return
        visited.add(node.name)
        
        if not node.is_external and node.class_info:
            bases_str = ", ".join(node.class_info.bases) if node.class_info.bases else "object"
            
            comp_list = []
            if show_composition:
                for attr, comp_node in sorted(node.resolved_composition.items()):
                    comp_list.append(f"{attr}: {comp_node.name}")
                for attr, ext_type in sorted(node.external_composition.items()):
                    clean_ext = ext_type.split(".")[-1]
                    comp_list.append(f"{attr}: {clean_ext}")
                    
            comp_str = ", ".join(comp_list) if comp_list else "-"
            
            rows.append((node.name, node.module, bases_str, comp_str))
            
        for sub in node.subclasses:
            collect_rows(sub)
            
    collect_rows(root_node)
    
    # Sort table rows alphabetically by class name
    for name, module, bases, comp in sorted(rows, key=lambda x: x[0]):
        if show_composition:
            table.add_row(name, module, bases, comp)
        else:
            table.add_row(name, module, bases)
            
    console.print(table)
