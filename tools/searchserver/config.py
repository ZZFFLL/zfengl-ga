import importlib

from .base import ProviderConfig


def _as_key_list(value):
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return []


def _load_mykey_module():
    try:
        import mykey
    except ImportError as exc:
        if getattr(exc, "name", None) == "mykey":
            return None
        raise
    return importlib.reload(mykey)


def _discover_provider_classes():
    from .registry import discover_provider_classes

    return discover_provider_classes()


def load_provider_configs(module=None, provider_classes=None):
    module = module if module is not None else _load_mykey_module()
    if module is None:
        return {}

    provider_classes = provider_classes if provider_classes is not None else _discover_provider_classes()
    providers = {}
    for name, cls in provider_classes.items():
        prefix = str(getattr(cls, "config_prefix", "") or name).strip()
        keys = _as_key_list(getattr(module, f"{prefix}_search_keys", None))
        url = str(getattr(module, f"{prefix}_search_url", "") or "").strip()
        if not keys and not url:
            continue
        providers[name] = ProviderConfig(
            name=name,
            type=str(getattr(cls, "type", "") or "").strip(),
            keys=keys,
            url=url,
        )
    return providers
