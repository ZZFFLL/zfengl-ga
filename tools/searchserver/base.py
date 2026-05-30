from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    name: str
    type: str = ""
    keys: list[str] = field(default_factory=list)
    url: str = ""
    timeout: int = 15


class ProviderError(Exception):
    pass


class SearchProvider:
    name = ""
    type = ""
    config_prefix = ""
    abstract = False

    def search(self, query, result_count):
        raise NotImplementedError


def normalize_results(items):
    results = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        normalized = {
            "title": str(item.get("title") or item.get("name") or item.get("url") or ""),
            "url": str(item.get("url") or item.get("link") or ""),
        }
        content = item.get("content") or item.get("snippet") or item.get("description")
        if content:
            normalized["content"] = str(content)
        for key in ("media", "icon", "publish_date", "refer"):
            if item.get(key) not in (None, ""):
                normalized[key] = item.get(key)
        if item.get("score") is not None:
            normalized["score"] = item.get("score")
        results.append(normalized)
    return results


def success_payload(provider, query, results):
    return {
        "status": "success",
        "provider": provider,
        "query": query,
        "results": normalize_results(results),
    }


def format_provider_errors(provider_errors):
    lines = []
    for item in provider_errors or []:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "searchserver")
        error = str(item.get("error") or "")
        lines.append(f"{provider}: {error}")
    return "\n".join(lines) or "searchserver: no provider error detail"


def all_failed_payload(query, provider_errors):
    return {
        "status": "error",
        "msg": format_provider_errors(provider_errors),
        "query": query,
        "provider_errors": provider_errors,
    }
