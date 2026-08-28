import requests

from ..base import ProviderError, SearchProvider, success_payload


class ZhipuProvider(SearchProvider):
    name = "zhipu"
    type = "国内数据全能"
    search_engine = "search_pro"

    def __init__(self, config, http_post=None):
        self.config = config
        self.http_post = http_post or _post_json

    def search(self, query, result_count):
        if not self.config.url:
            raise ProviderError("missing zhipu_search_url")
        if not self.config.keys:
            raise ProviderError("missing zhipu_search_keys")

        failures = []
        payload = self._build_payload(query, result_count)
        for idx, key in enumerate(self.config.keys, start=1):
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            try:
                data = self.http_post(self.config.url, payload, headers, self.config.timeout)
                api_error = _extract_api_error(data)
                if api_error:
                    raise ProviderError(api_error)
                results = data.get("search_result") if isinstance(data, dict) else []
                return success_payload(self.name, query, results)
            except Exception as exc:
                failures.append(f"key {idx}: {_sanitize_error(exc, key)}")
        raise ProviderError("; ".join(failures))

    def _build_payload(self, query, result_count):
        try:
            count = min(max(1, int(result_count)), 50)
        except (TypeError, ValueError) as exc:
            raise ProviderError("result_count must be an integer") from exc
        return {
            "search_engine": self.search_engine,
            "search_query": query,
            "count": count,
        }


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
    if isinstance(detail, dict):
        for key in ("error", "message", "msg"):
            if detail.get(key):
                return str(detail.get(key))
    for key in ("error", "message", "msg"):
        if data.get(key):
            return str(data.get(key))
    return ""


def _sanitize_error(exc, key):
    text = str(exc)
    return text.replace(str(key), "<redacted>") if key else text
