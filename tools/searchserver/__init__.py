from . import base, config, registry
from .base import ProviderError


def search(keyword, provider_names=None, providers=None):
    query = str(keyword or "").strip()
    if not query:
        return base.all_failed_payload(query, [{"provider": "searchserver", "error": "keyword is required"}])

    unavailable = []
    if providers is None:
        try:
            providers, unavailable = registry.build_providers(provider_names=provider_names)
        except Exception as exc:
            return base.all_failed_payload(query, [{"provider": "searchserver", "error": str(exc)}])

    provider_errors = list(unavailable)
    for provider in providers or []:
        name = getattr(provider, "name", provider.__class__.__name__)
        try:
            result = provider.search(query)
            if isinstance(result, dict) and result.get("status") == "success":
                return result
            raise ProviderError("provider returned non-success payload")
        except ProviderError as exc:
            provider_errors.append({"provider": name, "error": str(exc)})
        except Exception as exc:
            provider_errors.append({"provider": name, "error": str(exc)})

    return base.all_failed_payload(query, provider_errors)
