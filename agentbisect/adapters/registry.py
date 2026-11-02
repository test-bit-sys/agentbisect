"""
Contributor-friendly dynamic Adapter Registry for AgentBisect.
Enables contributors to easily plug in new agent transcript formats with a simple decorator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional, Type
from agentbisect.adapters.base import BaseAdapter

_REGISTRY: Dict[str, Type[BaseAdapter]] = {}


def register_adapter(cls: Type[BaseAdapter]) -> Type[BaseAdapter]:
    """Decorator to register a transcript adapter into the global registry."""
    if not issubclass(cls, BaseAdapter):
        raise TypeError(f"Adapter {cls.__name__} must inherit from BaseAdapter.")
    _REGISTRY[cls.name] = cls
    return cls


def get_adapter(name: str) -> Optional[Type[BaseAdapter]]:
    """Retrieves an adapter by name from the registry."""
    return _REGISTRY.get(name)


def list_registered_adapters() -> List[str]:
    """Returns the names of all currently registered adapters."""
    return list(_REGISTRY.keys())


def detect_adapter(file_path: Path) -> Optional[Type[BaseAdapter]]:
    """Finds the first registered adapter capable of handling the file, prioritizing specific formats over generic fallback."""
    specific = [cls for name, cls in _REGISTRY.items() if name != "generic_json"]
    fallback = [cls for name, cls in _REGISTRY.items() if name == "generic_json"]
    for adapter_cls in specific + fallback:
        try:
            if adapter_cls.can_handle(file_path):
                return adapter_cls
        except Exception:
            continue
    return None
