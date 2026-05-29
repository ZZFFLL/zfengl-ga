import importlib
import inspect
import pkgutil

from . import config as config_loader
from .base import SearchProvider
from . import providers as providers_pkg


def discover_provider_classes():
    classes = {}
    for module_info in pkgutil.iter_modules(providers_pkg.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{providers_pkg.__name__}.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is SearchProvider or not issubclass(obj, SearchProvider):
                continue
            name = getattr(obj, "name", None) or module_info.name
            classes[name] = obj
    return classes


def build_providers(provider_names=None, configs=None):
    names = set(provider_names or [])
    configs = configs if configs is not None else config_loader.load_provider_configs()
    classes = discover_provider_classes()
    providers = []
    unavailable = []

    for name, cls in classes.items():
        if names and name not in names:
            continue
        cfg = configs.get(name)
        if not cfg:
            unavailable.append({"provider": name, "error": "not configured"})
            continue
        try:
            providers.append(cls(cfg))
        except Exception as exc:
            unavailable.append({"provider": name, "error": str(exc)})

    for name in names - set(classes):
        unavailable.append({"provider": name, "error": "provider not found"})
    return providers, unavailable
