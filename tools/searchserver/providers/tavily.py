import requests

from ..base import ProviderError, SearchProvider, success_payload


class TavilyProvider(SearchProvider):
    name = "tavily"
    type = "国外数据全能"

    def __init__(self, config, http_post=None):
        self.config = config
        self.http_post = http_post or _post_json

    def search(self, query, result_count):
        if not self.config.url:
            raise ProviderError("missing tavily_search_url")
        if not self.config.keys:
            raise ProviderError("missing tavily_search_keys")

        failures = []
        try:
            max_results = min(max(1, int(result_count)), 50)
        except (TypeError, ValueError) as exc:
            raise ProviderError("result_count must be an integer") from exc
        payload = {"query": query, "search_depth": "basic", "max_results": max_results}
        for idx, key in enumerate(self.config.keys, start=1):
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            try:
                data = self.http_post(self.config.url, payload, headers, self.config.timeout)
                if isinstance(data, dict) and data.get("error"):
                    raise ProviderError(str(data.get("error")))
                results = data.get("results") if isinstance(data, dict) else []
                return success_payload(self.name, query, results)
            except Exception as exc:
                failures.append(f"key {idx}: {_sanitize_error(exc, key)}")
        raise ProviderError("; ".join(failures))


def _post_json(url, payload, headers, timeout):
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise ProviderError(str(exc)) from exc
    except ValueError as exc:
        raise ProviderError(f"invalid JSON response: {exc}") from exc


def _sanitize_error(exc, key):
    text = str(exc)
    return text.replace(str(key), "<redacted>") if key else text
