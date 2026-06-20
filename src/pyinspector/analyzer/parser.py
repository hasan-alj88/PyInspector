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
class PropertyInfo:
    name: str
    type_hint: Optional[str]
    source: str  # "init" or "property"

@dataclass
class ClassInfo:
    name: str
    signature: str
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)
    bases: List[str] = field(default_factory=list)
    composes: Dict[str, str] = field(default_factory=dict)
    properties: List[PropertyInfo] = field(default_factory=list)

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

def extract_composition(class_node: ast.ClassDef) -> Dict[str, str]:
    """Statically identifies composed class types from variable annotations and assignments."""
    composes = {}
    
    def get_type_name(expr_node) -> Optional[str]:
        if isinstance(expr_node, ast.Name):
            return expr_node.id
        elif isinstance(expr_node, ast.Attribute):
            return ast.unparse(expr_node)
        elif isinstance(expr_node, ast.Subscript):
            names = []
            for sub in ast.walk(expr_node.slice):
                if isinstance(sub, ast.Name):
                    names.append(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.append(ast.unparse(sub))
            if names:
                return names[0]
        return None

    for child in class_node.body:
        # Class-level annotations: e.g. adapter: HTTPAdapter
        if isinstance(child, ast.AnnAssign):
            if isinstance(child.target, ast.Name):
                t_name = get_type_name(child.annotation)
                if t_name:
                    composes[child.target.id] = t_name
                    
        # Methods: scan constructor parameter annotations & instantiations
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in child.args.args:
                if arg.arg != "self" and arg.annotation:
                    t_name = get_type_name(arg.annotation)
                    if t_name:
                        composes[arg.arg] = t_name
                        
            for sub_node in ast.walk(child):
                # self.headers = CaseInsensitiveDict()
                if isinstance(sub_node, ast.Assign):
                    for target in sub_node.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            if isinstance(sub_node.value, ast.Call):
                                func_name = get_type_name(sub_node.value.func)
                                if func_name:
                                    composes[target.attr] = func_name
                                    
                # self.adapter: HTTPAdapter = ...
                elif isinstance(sub_node, ast.AnnAssign):
                    if isinstance(sub_node.target, ast.Attribute) and isinstance(sub_node.target.value, ast.Name) and sub_node.target.value.id == "self":
                        t_name = get_type_name(sub_node.annotation)
                        if t_name:
                            composes[sub_node.target.attr] = t_name
                            
    return composes

def extract_properties(class_node: ast.ClassDef) -> List[PropertyInfo]:
    """Statically identifies class properties/attributes (via init and @property)."""
    properties = []
    
    # 1. Properties via @property and @cached_property getters
    for child in class_node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            is_prop = False
            for dec in child.decorator_list:
                if isinstance(dec, ast.Name) and dec.id in ("property", "cached_property"):
                    is_prop = True
                elif isinstance(dec, ast.Attribute) and dec.attr in ("property", "cached_property"):
                    is_prop = True
            
            if is_prop:
                type_hint = None
                if child.returns:
                    type_hint = ast.unparse(child.returns)
                properties.append(PropertyInfo(
                    name=child.name,
                    type_hint=type_hint,
                    source="property"
                ))

    # Helper to clean/unparse types
    def get_type_name(expr_node) -> Optional[str]:
        try:
            return ast.unparse(expr_node)
        except Exception:
            return None

    # 2. Properties via class-level attributes & init constructor assignments
    init_props = {}
    
    # 2a. Class-level annotations & assignments (source="class")
    for child in class_node.body:
        if isinstance(child, ast.AnnAssign):
            if isinstance(child.target, ast.Name):
                name = child.target.id
                t_hint = get_type_name(child.annotation)
                init_props[name] = (t_hint, "class")
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    init_props[name] = (None, "class")

    # 2b. Constructor assignments (source="init")
    for child in class_node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__init__":
            for sub_node in ast.walk(child):
                # self.x: T = ... or self.x: T
                if isinstance(sub_node, ast.AnnAssign):
                    if isinstance(sub_node.target, ast.Attribute) and isinstance(sub_node.target.value, ast.Name) and sub_node.target.value.id == "self":
                        name = sub_node.target.attr
                        t_hint = get_type_name(sub_node.annotation)
                        init_props[name] = (t_hint, "init")
                # self.x = ...
                elif isinstance(sub_node, ast.Assign):
                    for target in sub_node.targets:
                        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                            name = target.attr
                            if name not in init_props or init_props[name][0] is None:
                                init_props[name] = (None, "init")
                                
    for name, (t_hint, source) in init_props.items():
        properties.append(PropertyInfo(
            name=name,
            type_hint=t_hint,
            source=source
        ))
        
    return properties

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
            bases = [ast.unparse(b) for b in node.bases]
            composes = extract_composition(node)
            properties = extract_properties(node)
            
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
                methods=methods,
                bases=bases,
                composes=composes,
                properties=properties
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
        if package_path.endswith((".py", ".pyi")):
            canonical_path = os.path.realpath(package_path)
            visited_paths[canonical_path] = package_name
            mod_info = parse_file(package_path, package_name)
            mod_info.relative_path = os.path.basename(package_path)
            pkg.modules[package_name] = mod_info
            
    elif os.path.isdir(package_path):
        visited_paths[os.path.realpath(package_path)] = package_name
        candidate_files = {}
        
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
            
            # 2. Collect candidate files
            for file in files:
                if file.endswith((".py", ".pyi")):
                    full_path = os.path.join(root, file)
                    file_mod_name = get_module_name(full_path)
                    if not file_mod_name:
                        continue
                    
                    if file_mod_name not in candidate_files:
                        candidate_files[file_mod_name] = full_path
                    else:
                        existing_path = candidate_files[file_mod_name]
                        if file.endswith(".pyi") and existing_path.endswith(".py"):
                            candidate_files[file_mod_name] = full_path

        # 3. Process candidate files
        for file_mod_name, full_path in sorted(candidate_files.items()):
            canonical_file = os.path.realpath(full_path)
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
