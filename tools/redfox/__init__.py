"""RedFox 红狐数据平台 SDK 封装（GA 内置工具 redfox 的后端）。

统一入口 call(platform, action, params)：
  platform: douyin / xiaohongshu / wechat / bilibili / toutiao / tiktok /
            kuaishou / wechat_channels / youtube / twitter / instagram /
            dongchedi / yiche / autohome / hotspot / gpt_image /
            doubao_image / doubao_video / ai_search / tools
  action  : 平台对应方法名，如 search_articles / get_work / get_user_works ...
  params  : 该方法的关键字参数（键值对）

API Key 获取优先级：
  1. 环境变量 REDFOX_API_KEY（SDK 原生零配置）
  2. GA keychain 中的 redfox_api_key（SecretStr，不打印原始值）
"""
import os
import inspect


PLATFORMS = [
    "douyin", "xiaohongshu", "wechat", "bilibili", "toutiao", "tiktok",
    "kuaishou", "wechat_channels", "youtube", "twitter", "instagram",
    "dongchedi", "yiche", "autohome", "hotspot", "gpt_image",
    "doubao_image", "doubao_video", "ai_search", "tools",
]


def _load_keychain_keys():
    """按文件路径加载 GA keychain（避免 sys.path 依赖）。失败返回 None。"""
    try:
        import importlib.util
        _here = os.path.dirname(os.path.abspath(__file__))
        ga_root = os.path.dirname(os.path.dirname(_here))  # tools/redfox -> ga-tools
        kc_path = os.path.join(ga_root, "memory", "keychain.py")
        if not os.path.exists(kc_path):
            return None
        spec = importlib.util.spec_from_file_location("ga_keychain", kc_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.keys
    except Exception:
        return None


def _get_api_key():
    key = os.getenv("REDFOX_API_KEY", "").strip()
    if key:
        return key
    keys = _load_keychain_keys()
    if keys is not None:
        try:
            return keys.redfox_api_key.use()
        except (KeyError, AttributeError):
            pass
    return ""


def _make_client(api_key=None):
    from redfox import RedFoxClient
    key = api_key or _get_api_key()
    if not key:
        raise ValueError(
            "REDFOX_API_KEY 未配置。请用 GA keychain 存 redfox_api_key，"
            "或设置环境变量 REDFOX_API_KEY"
        )
    return RedFoxClient(api_key=key)


def _method_info(m, f):
    """方法签名 + docstring 摘要（summary + :param 行），供模型自省参数格式。"""
    sig = f"{m}{inspect.signature(f)}"
    doc = inspect.getdoc(f) or ""
    summary = ""
    for line in doc.splitlines():
        line = line.strip()
        if not line or line.startswith(":param") or line.startswith(":return"):
            break
        summary += line + " "
    summary = summary.strip()
    params = [ln.strip() for ln in doc.splitlines() if ln.strip().startswith(":param")]
    parts = [sig]
    if summary:
        parts.append(summary)
    if params:
        parts.extend(params)
    return " | ".join(parts)


def list_actions(platform):
    """返回某平台全部公开方法签名+docstring说明（供模型自省，也方便排查）。"""
    try:
        from redfox import RedFoxClient
    except ImportError as exc:
        return {"status": "error", "msg": f"redfox SDK 未安装: {exc}"}
    if platform not in PLATFORMS:
        return {"status": "error", "msg": f"未知平台 {platform}，可选：{PLATFORMS}"}
    # 用 probe key 实例化即可拿到模块结构，不触发任何网络请求
    client = RedFoxClient(api_key="probe")
    mod = getattr(client, platform, None)
    if mod is None:
        return {"status": "error", "msg": f"未知平台 {platform}"}
    methods = []
    for m in dir(mod.__class__):
        if m.startswith("_"):
            continue
        f = getattr(mod.__class__, m, None)
        if callable(f):
            try:
                methods.append(_method_info(m, f))
            except Exception:
                methods.append(m)
    return {"status": "success", "platform": platform, "methods": methods}


def call(platform, action, params=None):
    """调用 RedFox SDK 的 platform.action(**params)。"""
    platform = str(platform or "").strip()
    action = str(action or "").strip()
    if platform not in PLATFORMS:
        return {"status": "error", "msg": f"未知平台 {platform}，可选：{PLATFORMS}"}
    if action == "__methods__":
        return list_actions(platform)
    if not action:
        return {"status": "error", "msg": "action 不能为空（可用 action='__methods__' 枚举）"}
    params = params or {}
    if not isinstance(params, dict):
        return {"status": "error", "msg": "params 必须是对象(键值对)"}
    try:
        client = _make_client()
    except Exception as exc:
        return {"status": "error", "msg": str(exc)}
    try:
        mod = getattr(client, platform, None)
        if mod is None:
            return {"status": "error", "msg": f"未知平台 {platform}"}
        fn = getattr(mod, action, None)
        if fn is None or not callable(fn):
            return {"status": "error", "msg": f"平台 {platform} 无动作 {action}（可用 action='__methods__' 枚举）"}
        result = fn(**params)
        return {"status": "success", "platform": platform, "action": action, "data": result}
    except Exception as exc:
        return {"status": "error", "msg": f"{type(exc).__name__}: {exc}"}
    finally:
        try:
            client.close()
        except Exception:
            pass
