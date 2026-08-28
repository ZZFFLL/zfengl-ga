from . import base, config, registry
from .base import ProviderError


def _filter_providers_by_type(providers, provider_types):
    types = {str(item).strip() for item in provider_types or [] if str(item).strip()}
    if not types:
        return list(providers or [])
    return [provider for provider in providers or [] if str(getattr(provider, "type", "") or "").strip() in types]


def search(keyword, result_count, provider_names=None, provider_types=None, providers=None):
    query = str(keyword or "").strip()
    if not query:
        return base.all_failed_payload(query, [{"provider": "searchserver", "error": "keyword is required"}])
    requested_types = [str(item).strip() for item in (provider_types or []) if str(item).strip()]
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
    providers = _filter_providers_by_type(providers, requested_types)
    if requested_types and not providers and not provider_errors:
        provider_errors.append({"provider": "searchserver", "error": f"no provider matched type: {requested_types[0]}"})
    for provider in providers:
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
