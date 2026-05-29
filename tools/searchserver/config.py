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


def load_provider_configs(module=None):
    module = module if module is not None else _load_mykey_module()
    if module is None:
        return {}

    providers = {}
    tavily_keys = _as_key_list(getattr(module, "tavily_search_keys", None))
    tavily_url = str(getattr(module, "tavily_search_url", "") or "").strip()
    if tavily_keys or tavily_url:
        providers["tavily"] = ProviderConfig(name="tavily", keys=tavily_keys, url=tavily_url)
    return providers
