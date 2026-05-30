import requests

from ..base import ProviderError, SearchProvider, success_payload


class TavilyBaseProvider(SearchProvider):
    abstract = True
    config_prefix = "tavily"
    search_depth = "basic"
    topic = ""
    extra_payload = {}

    def __init__(self, config, http_post=None):
        self.config = config
        self.http_post = http_post or _post_json

    def search(self, query, result_count):
        if not self.config.url:
            raise ProviderError("missing tavily_search_url")
        if not self.config.keys:
            raise ProviderError("missing tavily_search_keys")

        failures = []
        payload = self._build_payload(query, result_count)
        for idx, key in enumerate(self.config.keys, start=1):
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            try:
                data = self.http_post(self.config.url, payload, headers, self.config.timeout)
                api_error = _extract_api_error(data)
                if api_error:
                    raise ProviderError(api_error)
                results = data.get("results") if isinstance(data, dict) else []
                return success_payload(self.name, query, results)
            except Exception as exc:
                failures.append(f"key {idx}: {_sanitize_error(exc, key)}")
        raise ProviderError("; ".join(failures))

    def _build_payload(self, query, result_count):
        try:
            max_results = min(max(1, int(result_count)), 20)
        except (TypeError, ValueError) as exc:
            raise ProviderError("result_count must be an integer") from exc
        payload = {"query": query, "search_depth": self.search_depth, "max_results": max_results}
        if self.topic:
            payload["topic"] = self.topic
        payload.update(self.extra_payload)
        return payload


class TavilyProvider(TavilyBaseProvider):
    abstract = False
    name = "tavily"
    type = "国外数据全能"


class TavilyDeepProvider(TavilyBaseProvider):
    abstract = False
    name = "tavily_deep"
    type = "国外深度数据"
    search_depth = "advanced"
    extra_payload = {"chunks_per_source": 3}


class TavilyNewsProvider(TavilyBaseProvider):
    abstract = False
    name = "tavily_news"
    type = "国外新闻"
    topic = "news"


class TavilyFinanceProvider(TavilyBaseProvider):
    abstract = False
    name = "tavily_finance"
    type = "国外金融"
    topic = "finance"


def _post_json(url, payload, headers, timeout):
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            api_error = _extract_response_error(response)
            raise ProviderError(api_error or str(exc)) from exc
        return response.json()
    except requests.RequestException as exc:
        raise ProviderError(str(exc)) from exc
    except ValueError as exc:
        raise ProviderError(f"invalid JSON response: {exc}") from exc


def _extract_response_error(response):
    try:
        return _extract_api_error(response.json())
    except Exception:
        return ""


def _extract_api_error(data):
    if not isinstance(data, dict):
        return ""
    detail = data.get("detail")
    if isinstance(detail, dict) and detail.get("error"):
        return str(detail.get("error"))
    if data.get("error"):
        return str(data.get("error"))
    return ""


def _sanitize_error(exc, key):
    text = str(exc)
    return text.replace(str(key), "<redacted>") if key else text
