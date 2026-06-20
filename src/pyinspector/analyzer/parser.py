import os
import ast
import copy
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class FunctionInfo:
    name: str
    signature: str
    docstring: Optional[str]
    is_async: bool
    is_method: bool = False
    is_deprecated: bool = False
    deprecation_reason: Optional[str] = None
    is_unexposed: bool = False
    missing_from_all: bool = False

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
    is_unexposed: bool = False
    missing_from_all: bool = False

@dataclass
class ModuleInfo:
    name: str  # Full module name (e.g., requests.models)
    relative_path: str  # Path relative to package root
    classes: List[ClassInfo] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    is_recursive: bool = False
    points_to: Optional[str] = None
    imported_names: Dict[str, tuple[Optional[str], str]] = field(default_factory=dict)
    declared_all: Optional[List[str]] = None
    star_imports: List[str] = field(default_factory=list)

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

def extract_deprecation_info(node: ast.FunctionDef | ast.AsyncFunctionDef, docstring: Optional[str]) -> tuple[bool, Optional[str]]:
    """Statically checks decorators, function body warnings, and docstrings for deprecation warnings."""
    is_deprecated = False
    reason = None
    
    # 1. Inspect Decorators
    if node.decorator_list:
        for dec in node.decorator_list:
            dec_name = ""
            args = []
            if isinstance(dec, ast.Name):
                dec_name = dec.id
            elif isinstance(dec, ast.Attribute):
                dec_name = ast.unparse(dec)
            elif isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                elif isinstance(dec.func, ast.Attribute):
                    dec_name = ast.unparse(dec.func)
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        args.append(arg.value)
                for kw in dec.keywords:
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value, str):
                        args.append(kw.value)
            
            dec_name_lower = dec_name.lower()
            if "deprecated" in dec_name_lower or "warn" in dec_name_lower:
                is_deprecated = True
                if args:
                    reason = args[0]
                    break
                    
    # 2. Inspect Function Body for warnings.warn / warnings.warn_explicit
    if not is_deprecated:
        try:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func_name = ast.unparse(child.func)
                    if "warn" in func_name.lower():
                        warn_args = []
                        is_dep_warning = False
                        for arg in child.args:
                            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                                warn_args.append(arg.value)
                            elif isinstance(arg, ast.Name) and "deprecation" in arg.id.lower():
                                is_dep_warning = True
                        for kw in child.keywords:
                            if isinstance(kw.value, ast.Constant) and isinstance(kw.value, str):
                                warn_args.append(kw.value)
                            elif isinstance(kw.value, ast.Name) and "deprecation" in kw.value.id.lower():
                                is_dep_warning = True
                                
                        if is_dep_warning or any("deprecated" in a.lower() or "deprecation" in a.lower() for a in warn_args):
                            is_deprecated = True
                            if warn_args:
                                reason = warn_args[0]
                            break
        except Exception:
            pass

    # 3. Inspect Docstring
    if docstring:
        for line in docstring.splitlines():
            line_strip = line.strip()
            line_lower = line_strip.lower()
            is_dep_line = (
                line_lower.startswith("deprecated") or
                line_strip.startswith(".. deprecated::") or
                "@deprecated" in line_strip
            )
            if is_dep_line:
                is_deprecated = True
                if not reason:
                    reason_candidate = line_strip
                    if reason_candidate.startswith(".. deprecated::"):
                        reason_candidate = reason_candidate[15:].strip()
                    elif reason_candidate.lower().startswith("deprecated:"):
                        reason_candidate = reason_candidate[11:].strip()
                    elif reason_candidate.lower().startswith("deprecated"):
                        reason_candidate = reason_candidate[10:].strip()
                    if reason_candidate:
                        reason = reason_candidate
                break
                
    return is_deprecated, reason

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
    imported_names = {}
    declared_all = None
    star_imports = []
    
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
                    is_dep, dep_reason = extract_deprecation_info(item, method_doc)
                    methods.append(FunctionInfo(
                        name=item.name,
                        signature=method_sig,
                        docstring=method_doc,
                        is_async=is_async,
                        is_method=True,
                        is_deprecated=is_dep,
                        deprecation_reason=dep_reason
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
            is_dep, dep_reason = extract_deprecation_info(node, func_doc)
            functions.append(FunctionInfo(
                name=node.name,
                signature=func_sig,
                docstring=func_doc,
                is_async=is_async,
                is_method=False,
                is_deprecated=is_dep,
                deprecation_reason=dep_reason
            ))
            
        elif isinstance(node, ast.Import):
            for alias in node.names:
                exposed = alias.asname or alias.name
                imported_names[exposed] = (None, alias.name)
                
        elif isinstance(node, ast.ImportFrom):
            module_src = ""
            if node.level > 0:
                module_src = "." * node.level
            if node.module:
                module_src += node.module
            for alias in node.names:
                if alias.name == "*":
                    star_imports.append(module_src)
                else:
                    exposed = alias.asname or alias.name
                    imported_names[exposed] = (module_src, alias.name)
                
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        declared_all = []
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                declared_all.append(elt.value)
                            elif isinstance(elt, ast.Name):
                                declared_all.append(elt.id)
            
    return ModuleInfo(
        name=module_name,
        relative_path=file_path,
        classes=classes,
        functions=functions,
        imported_names=imported_names,
        declared_all=declared_all,
        star_imports=star_imports
    )

def analyze_package(package_name: str, package_path: str) -> PackageInfo:
    """Recursively scans a package directory or file and constructs a PackageInfo tree, detecting circular loops."""
    pkg_path = Path(package_path)
    pkg = PackageInfo(name=package_name, path=str(pkg_path))
    
    # Track visited paths: realpath -> module_name
    visited_paths = {}
    
    parent_dir = pkg_path.parent
    
    def get_module_name(target_path: Path) -> str:
        try:
            rel_path = target_path.relative_to(parent_dir)
        except ValueError:
            rel_path = target_path
            
        parts = list(rel_path.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts.pop()
        if parts:
            parts[0] = package_name
        return ".".join(parts)

    if pkg_path.is_file():
        if pkg_path.suffix in (".py", ".pyi"):
            canonical_path = str(pkg_path.resolve())
            visited_paths[canonical_path] = package_name
            mod_info = parse_file(str(pkg_path), package_name)
            mod_info.relative_path = pkg_path.name
            pkg.modules[package_name] = mod_info
            
    elif pkg_path.is_dir():
        visited_paths[str(pkg_path.resolve())] = package_name
        candidate_files = {}
        
        for root, dirs, files in os.walk(str(pkg_path), followlinks=True):
            root_path = Path(root)
            # 1. Clean directories & check for folder loops
            remaining_dirs = []
            for d in dirs:
                if d.startswith(".") or d == "__pycache__":
                    continue
                dir_path = root_path / d
                canonical_dir = str(dir_path.resolve())
                
                if canonical_dir in visited_paths:
                    loop_mod_name = get_module_name(dir_path)
                    if loop_mod_name:
                        pkg.modules[loop_mod_name] = ModuleInfo(
                            name=loop_mod_name,
                            relative_path=str(dir_path.relative_to(pkg_path)),
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
                    full_path = root_path / file
                    file_mod_name = get_module_name(full_path)
                    if not file_mod_name:
                        continue
                    
                    if file_mod_name not in candidate_files:
                        candidate_files[file_mod_name] = full_path
                    else:
                        existing_path = candidate_files[file_mod_name]
                        if file.endswith(".pyi") and existing_path.name.endswith(".py"):
                            candidate_files[file_mod_name] = full_path

        # 3. Process candidate files
        for file_mod_name, full_path in sorted(candidate_files.items()):
            canonical_file = str(full_path.resolve())
            if canonical_file in visited_paths:
                pkg.modules[file_mod_name] = ModuleInfo(
                    name=file_mod_name,
                    relative_path=str(full_path.relative_to(pkg_path)),
                    is_recursive=True,
                    points_to=visited_paths[canonical_file]
                )
            else:
                visited_paths[canonical_file] = file_mod_name
                mod_info = parse_file(str(full_path), file_mod_name)
                mod_info.relative_path = str(full_path.relative_to(pkg_path))
                pkg.modules[file_mod_name] = mod_info
                        
    check_api_exposure(pkg)
    return pkg

def check_api_exposure(pkg: PackageInfo):
    """Post-processes the package to detect unexposed API items and missing __all__ exports."""
    def resolve_module_name(parent_name: str, module_src: Optional[str]) -> str:
        if not module_src:
            return ""
        if module_src.startswith("."):
            level = 0
            for char in module_src:
                if char == '.':
                    level += 1
                else:
                    break
            sub_name = module_src[level:]
            parts = parent_name.split(".")
            if level > len(parts):
                return sub_name
            base_parts = parts[:len(parts) - (level - 1)]
            if sub_name:
                return ".".join(base_parts + [sub_name])
            else:
                return ".".join(base_parts)
        else:
            return module_src

    for mod_name, mod in pkg.modules.items():
        # First, check items defined directly in this module for missing_from_all if it has __all__
        if mod.declared_all is not None:
            for c in mod.classes:
                if not c.name.startswith("_"):
                    if c.name not in mod.declared_all:
                        c.missing_from_all = True
            for f in mod.functions:
                if not f.name.startswith("_"):
                    if f.name not in mod.declared_all:
                        f.missing_from_all = True

        # Now, if it's a submodule, check exposure in its parent __init__.py
        if "." in mod_name:
            parts = mod_name.split(".")
            parent_name = ".".join(parts[:-1])
            parent_mod = pkg.modules.get(parent_name)
            if parent_mod is not None:
                # Check classes
                for c in mod.classes:
                    if c.name.startswith("_"):
                        continue
                    
                    is_star_imported = any(
                        resolve_module_name(parent_mod.name, src) == mod_name
                        for src in parent_mod.star_imports
                    )
                    
                    explicit_exposed_names = [
                        exp_name
                        for exp_name, (src, orig) in parent_mod.imported_names.items()
                        if resolve_module_name(parent_mod.name, src) == mod_name and orig == c.name
                    ]
                    
                    if not is_star_imported and not explicit_exposed_names:
                        c.is_unexposed = True
                    else:
                        c.is_unexposed = False
                        if parent_mod.declared_all is not None:
                            exposed_names = []
                            if is_star_imported:
                                exposed_names.append(c.name)
                            exposed_names.extend(explicit_exposed_names)
                            
                            if not any(name in parent_mod.declared_all for name in exposed_names):
                                c.missing_from_all = True
                                
                # Check functions
                for f in mod.functions:
                    if f.name.startswith("_"):
                        continue
                    
                    is_star_imported = any(
                        resolve_module_name(parent_mod.name, src) == mod_name
                        for src in parent_mod.star_imports
                    )
                    
                    explicit_exposed_names = [
                        exp_name
                        for exp_name, (src, orig) in parent_mod.imported_names.items()
                        if resolve_module_name(parent_mod.name, src) == mod_name and orig == f.name
                    ]
                    
                    if not is_star_imported and not explicit_exposed_names:
                        f.is_unexposed = True
                    else:
                        f.is_unexposed = False
                        if parent_mod.declared_all is not None:
                            exposed_names = []
                            if is_star_imported:
                                exposed_names.append(f.name)
                            exposed_names.extend(explicit_exposed_names)
                            
                            if not any(name in parent_mod.declared_all for name in exposed_names):
                                f.missing_from_all = True
