# -*- coding: utf-8 -*-
"""publish 包:多平台统一发布编排。

Public entry points are resolved lazily so importing a lightweight submodule does
not initialize the publishing runtime and all of its optional dependencies.
"""
from importlib import import_module
from typing import Any


_PUBLIC_IMPORTS = {
    "PublishOverrides": ("publish.config", "PublishOverrides"),
    "main": ("publish.orchestrator", "main"),
    "run_publish": ("publish.orchestrator", "run_publish"),
    "run_publish_sync": ("publish.orchestrator", "run_publish_sync"),
}

__all__ = list(_PUBLIC_IMPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _PUBLIC_IMPORTS[name]
    except KeyError:
        raise AttributeError(
            "module {!r} has no attribute {!r}".format(__name__, name)
        ) from None
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
