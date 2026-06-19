import json
import yaml
from typing import Optional, Dict, Any
from rich.tree import Tree
from rich.text import Text
from rich.console import Console
from ..analyzer import PackageInfo, ModuleInfo, ClassInfo, FunctionInfo

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
