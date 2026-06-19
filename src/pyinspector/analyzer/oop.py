from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from .parser import PackageInfo, ClassInfo

@dataclass
class OOPClassNode:
    name: str
    module: str
    class_info: Optional[ClassInfo] = None
    subclasses: List['OOPClassNode'] = field(default_factory=list)
    # Maps attribute name -> composed class node
    resolved_composition: Dict[str, 'OOPClassNode'] = field(default_factory=dict)
    # Maps attribute name -> class name string (for external types)
    external_composition: Dict[str, str] = field(default_factory=dict)
    # Parent classes
    parents: List['OOPClassNode'] = field(default_factory=list)
    is_external: bool = False

    def __repr__(self):
        return f"<OOPClassNode {self.name} (external={self.is_external})>"

def resolve_class_node(
    name: str, 
    by_fullname: Dict[str, OOPClassNode], 
    by_shortname: Dict[str, List[OOPClassNode]]
) -> Optional[OOPClassNode]:
    """Helper to resolve a class name string to an existing class node."""
    if name in by_fullname:
        return by_fullname[name]
    
    # Try last part (short name)
    short = name.split(".")[-1]
    if short in by_shortname:
        return by_shortname[short][0]
        
    return None

def build_oop_graph(pkg_info: PackageInfo, include_external: bool = False) -> OOPClassNode:
    """
    Constructs an OOP inheritance and composition forest.
    Returns the root 'object' node.
    """
    root = OOPClassNode(name="object", module="", is_external=True)
    
    by_fullname: Dict[str, OOPClassNode] = {}
    by_shortname: Dict[str, List[OOPClassNode]] = {}
    
    # 1. First Pass: Create class nodes for all defined classes in the package
    for mod_name, mod_info in pkg_info.modules.items():
        if mod_info.is_recursive:
            continue
        for cls in mod_info.classes:
            fullname = f"{mod_name}.{cls.name}"
            node = OOPClassNode(name=cls.name, module=mod_name, class_info=cls)
            by_fullname[fullname] = node
            by_shortname.setdefault(cls.name, []).append(node)
            
    # Keep track of created external nodes to avoid duplicates
    external_nodes: Dict[str, OOPClassNode] = {}
    
    # 2. Second Pass: Resolve Inheritance (Bases)
    for node in list(by_fullname.values()):
        if not node.class_info:
            continue
            
        for base_name in node.class_info.bases:
            # Resolve parent
            parent = resolve_class_node(base_name, by_fullname, by_shortname)
            
            if parent:
                # Link internal parent
                if parent not in node.parents:
                    node.parents.append(parent)
                if node not in parent.subclasses:
                    parent.subclasses.append(node)
            elif include_external:
                # Resolve or create external parent
                short_base = base_name.split(".")[-1]
                if short_base not in external_nodes:
                    ext_node = OOPClassNode(name=base_name, module="", is_external=True)
                    external_nodes[short_base] = ext_node
                    # Link external parent to object root
                    root.subclasses.append(ext_node)
                    ext_node.parents.append(root)
                else:
                    ext_node = external_nodes[short_base]
                    
                if ext_node not in node.parents:
                    node.parents.append(ext_node)
                if node not in ext_node.subclasses:
                    ext_node.subclasses.append(node)
                    
    # 3. Third Pass: Resolve Composition
    for node in list(by_fullname.values()):
        if not node.class_info:
            continue
            
        for attr, target_type in node.class_info.composes.items():
            resolved = resolve_class_node(target_type, by_fullname, by_shortname)
            if resolved:
                node.resolved_composition[attr] = resolved
            else:
                node.external_composition[attr] = target_type
                
    # 4. Fourth Pass: Link classes without parents directly to 'object' root
    for node in list(by_fullname.values()):
        if not node.parents:
            root.subclasses.append(node)
            node.parents.append(root)
            
    return root
