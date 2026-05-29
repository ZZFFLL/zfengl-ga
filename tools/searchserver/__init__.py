from . import base, config, registry
from .base import ProviderError


def search(keyword, result_count, provider_names=None, provider_types=None, providers=None):
    query = str(keyword or "").strip()
    if not query:
        return base.all_failed_payload(query, [{"provider": "searchserver", "error": "keyword is required"}])
    try:
        result_count = int(result_count)
    except (TypeError, ValueError):
        return base.all_failed_payload(query, [{"provider": "searchserver", "error": "result_count is required"}])
    if result_count <= 0:
        return base.all_failed_payload(query, [{"provider": "searchserver", "error": "result_count must be greater than 0"}])

    unavailable = []
    if providers is None:
        try:
            providers, unavailable = registry.build_providers(provider_names=provider_names, provider_types=provider_types)
        except Exception as exc:
            return base.all_failed_payload(query, [{"provider": "searchserver", "error": str(exc)}])

    provider_errors = list(unavailable)
    for provider in providers or []:
        name = getattr(provider, "name", provider.__class__.__name__)
        try:
            result = provider.search(query, result_count)
            if isinstance(result, dict) and result.get("status") == "success":
                return result
            raise ProviderError("provider returned non-success payload")
        except ProviderError as exc:
            provider_errors.append({"provider": name, "error": str(exc)})
        except Exception as exc:
            provider_errors.append({"provider": name, "error": str(exc)})

    return base.all_failed_payload(query, provider_errors)
