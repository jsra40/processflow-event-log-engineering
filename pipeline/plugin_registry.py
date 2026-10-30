
from __future__ import annotations
from importlib import import_module

def load_plugin(spec: str):
    """Load 'module.path:ClassName' and instantiate it."""
    if ":" not in spec:
        raise ValueError("plugin must use 'module.path:ClassName'")
    module_name, class_name = spec.split(":",1)
    module=import_module(module_name)
    cls=getattr(module,class_name)
    return cls()
