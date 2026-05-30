from . import base, config, registry
from .base import ProviderError


NEWS_TERMS = ("新闻", "最新", "今日", "今天", "实时", "breaking", "latest", "today", "news")
FINANCE_TERMS = ("金融", "财经", "股票", "股价", "财报", "市值", "汇率", "crypto", "stock", "earnings", "finance")
DEEP_TERMS = ("深度", "详细", "分析", "报告", "原文", "research", "analysis", "detailed")


def _provider_score(provider, query):
    ptype = str(getattr(provider, "type", "") or "")
    text = str(query or "").lower()
    score = 0
    if "新闻" in ptype and any(term in text for term in NEWS_TERMS):
        score += 30
    if "金融" in ptype and any(term in text for term in FINANCE_TERMS):
        score += 30
    if "深度" in ptype and any(term in text for term in DEEP_TERMS):
        score += 20
    if "数据全能" in ptype:
        score += 10
    return score


def _rank_providers(providers, query):
    indexed = list(enumerate(providers or []))
    indexed.sort(key=lambda item: (-_provider_score(item[1], query), item[0]))
    return [provider for _, provider in indexed]


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
    for provider in _rank_providers(providers, query):
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
