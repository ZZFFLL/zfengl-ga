from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    name: str
    keys: list[str] = field(default_factory=list)
    url: str = ""
    timeout: int = 15


class ProviderError(Exception):
    pass


class SearchProvider:
    name = ""

    def search(self, query):
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


def all_failed_payload(query, provider_errors):
    return {
        "status": "error",
        "msg": "无法搜索: all providers failed",
        "query": query,
        "provider_errors": provider_errors,
    }
