import os
import ast
import copy
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class FunctionInfo:
    name: str
    signature: str
    docstring: Optional[str]
    is_async: bool
    is_method: bool = False

@dataclass
class ClassInfo:
    name: str
    signature: str
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)

@dataclass
class ModuleInfo:
    name: str  # Full module name (e.g., requests.models)
    relative_path: str  # Path relative to package root
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    is_recursive: bool = False
    points_to: Optional[str] = None

@dataclass
class PackageInfo:
    name: str
    path: str
    modules: Dict[str, ModuleInfo] = field(default_factory=dict)

def get_signature_func(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Extracts the function signature string via ast.unparse."""
    try:
        dummy = copy.copy(node)
        dummy.body = [ast.Pass()]
        dummy.decorator_list = []
        sig = ast.unparse(dummy)
        if sig.endswith(":\n    pass"):
            sig = sig[:-10]
        return sig
    except Exception:
        return f"def {node.name}(...)"

def get_signature_class(node: ast.ClassDef) -> str:
    """Extracts the class definition signature string via ast.unparse."""
    try:
        dummy = copy.copy(node)
        dummy.body = [ast.Pass()]
        dummy.decorator_list = []
        sig = ast.unparse(dummy)
        if sig.endswith(":\n    pass"):
            sig = sig[:-10]
        return sig
    except Exception:
        return f"class {node.name}"

def parse_file(file_path: str, module_name: str) -> ModuleInfo:
    """Statically parses a single python file and extracts all its classes and functions."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    try:
        tree = ast.parse(content, filename=file_path)
    except Exception as e:
        print(f"Warning: Failed to parse {file_path}: {e}", file=sys.stderr)
        return ModuleInfo(name=module_name, relative_path=file_path)
        
    classes = []
    functions = []
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = []
            class_doc = ast.get_docstring(node)
            class_sig = get_signature_class(node)
            
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_doc = ast.get_docstring(item)
                    method_sig = get_signature_func(item)
                    is_async = isinstance(item, ast.AsyncFunctionDef)
                    methods.append(FunctionInfo(
                        name=item.name,
                        signature=method_sig,
                        docstring=method_doc,
                        is_async=is_async,
                        is_method=True
                    ))
            
            classes.append(ClassInfo(
                name=node.name,
                signature=class_sig,
                docstring=class_doc,
                methods=methods
            ))
            
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_doc = ast.get_docstring(node)
            func_sig = get_signature_func(node)
            is_async = isinstance(node, ast.AsyncFunctionDef)
            functions.append(FunctionInfo(
                name=node.name,
                signature=func_sig,
                docstring=func_doc,
                is_async=is_async,
                is_method=False
            ))
            
    return ModuleInfo(
        name=module_name,
        relative_path=file_path,
        classes=classes,
        functions=functions
    )

def analyze_package(package_name: str, package_path: str) -> PackageInfo:
    """Recursively scans a package directory or file and constructs a PackageInfo tree, detecting circular loops."""
    pkg = PackageInfo(name=package_name, path=package_path)
    
    # Track visited paths: realpath -> module_name
    visited_paths = {}
    
    def get_module_name(target_path):
        parent_dir = os.path.dirname(package_path)
        if not parent_dir:
            parent_dir = "."
        rel_path = os.path.relpath(target_path, parent_dir)
        parts = os.path.splitext(rel_path)[0].split(os.sep)
        if parts and parts[-1] == "__init__":
            parts.pop()
        if parts:
            parts[0] = package_name
        return ".".join(parts)

    if os.path.isfile(package_path):
        if package_path.endswith(".py"):
            canonical_path = os.path.realpath(package_path)
            visited_paths[canonical_path] = package_name
            mod_info = parse_file(package_path, package_name)
            mod_info.relative_path = os.path.basename(package_path)
            pkg.modules[package_name] = mod_info
            
    elif os.path.isdir(package_path):
        visited_paths[os.path.realpath(package_path)] = package_name
        
        for root, dirs, files in os.walk(package_path, followlinks=True):
            # 1. Clean directories & check for folder loops
            remaining_dirs = []
            for d in dirs:
                if d.startswith(".") or d == "__pycache__":
                    continue
                dir_path = os.path.join(root, d)
                canonical_dir = os.path.realpath(dir_path)
                
                if canonical_dir in visited_paths:
                    loop_mod_name = get_module_name(dir_path)
                    if loop_mod_name:
                        pkg.modules[loop_mod_name] = ModuleInfo(
                            name=loop_mod_name,
                            relative_path=os.path.relpath(dir_path, package_path),
                            is_recursive=True,
                            points_to=visited_paths[canonical_dir]
                        )
                else:
                    loop_mod_name = get_module_name(dir_path)
                    if loop_mod_name:
                        visited_paths[canonical_dir] = loop_mod_name
                    remaining_dirs.append(d)
            dirs[:] = remaining_dirs
            
            # 2. Process files & check for file loops/duplicates
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    canonical_file = os.path.realpath(full_path)
                    file_mod_name = get_module_name(full_path)
                    
                    if not file_mod_name:
                        continue
                        
                    if canonical_file in visited_paths:
                        pkg.modules[file_mod_name] = ModuleInfo(
                            name=file_mod_name,
                            relative_path=os.path.relpath(full_path, package_path),
                            is_recursive=True,
                            points_to=visited_paths[canonical_file]
                        )
                    else:
                        visited_paths[canonical_file] = file_mod_name
                        mod_info = parse_file(full_path, file_mod_name)
                        mod_info.relative_path = os.path.relpath(full_path, package_path)
                        pkg.modules[file_mod_name] = mod_info
                        
    return pkg
