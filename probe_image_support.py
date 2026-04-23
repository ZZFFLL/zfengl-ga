
"""Probe whether the configured OpenAI-compatible API supports image input.

Usage:
  python probe_image_support.py --config ../mykey.py --key native_oai_config
  python probe_image_support.py --config ../mykey.py --key native_oai_config2

It will:
1) load the chosen config dict from mykey.py
2) send a minimal text-only request to verify the API works
3) send a minimal request containing a tiny 1x1 PNG as image input
4) report whether image input is accepted
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import pathlib
import sys
from typing import Any, Dict

import requests

PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO0n3r8AAAAASUVORK5CYII="
)


def load_module(path: str):
    p = pathlib.Path(path).resolve()
    spec = importlib.util.spec_from_file_location(p.stem, p)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module from {p}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def get_cfg(mod, key: str) -> Dict[str, Any]:
    cfg = getattr(mod, key, None)
    if not isinstance(cfg, dict):
        raise TypeError(f"{key} is not a dict")
    return cfg


def auto_url(base: str, path: str) -> str:
    b = base.rstrip('/')
    p = path.strip('/')
    if b.endswith('$'):
        return b[:-1].rstrip('/')
    if b.endswith(p):
        return b
    return f"{b}/{path.strip('/')}" if '/v' in b else f"{b}/v1/{path.strip('/')}"


def send_openai_compat(cfg: Dict[str, Any], messages, api_mode: str):
    base = cfg['apibase']
    key = cfg['apikey']
    model = cfg['model']
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    if api_mode == 'responses':
        url = auto_url(base, 'responses')
        payload = {
            'model': model,
            'input': messages,
            'stream': False,
        }
    else:
        url = auto_url(base, 'chat/completions')
        payload = {
            'model': model,
            'messages': messages,
            'stream': False,
        }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    return r


def text_only_messages(api_mode: str):
    if api_mode == 'responses':
        return [
            {'role': 'user', 'content': [{'type': 'input_text', 'text': 'reply with OK'}]},
        ]
    return [
        {'role': 'user', 'content': 'reply with OK'},
    ]


def image_messages(api_mode: str):
    if api_mode == 'responses':
        return [
            {
                'role': 'user',
                'content': [
                    {'type': 'input_text', 'text': 'describe the image in one word'},
                    {'type': 'input_image', 'image_url': f'data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}'},
                ],
            }
        ]
    return [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': 'describe the image in one word'},
                {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{base64.b64encode(PNG_1X1).decode()}'}},
            ],
        }
    ]


def main():
    ap = argparse.ArgumentParser()
    default_cfg = str((pathlib.Path(__file__).resolve().parent / 'mykey.py').resolve())
    ap.add_argument('--config', default=default_cfg)
    ap.add_argument('--key', default='native_oai_config')
    args = ap.parse_args()

    mod = load_module(args.config)
    cfg = get_cfg(mod, args.key)
    api_mode = str(cfg.get('api_mode', 'chat_completions')).strip().lower().replace('-', '_')
    api_mode = 'responses' if api_mode in ('responses', 'response') else 'chat_completions'

    print('config:', json.dumps({k: cfg.get(k) for k in ('name', 'apibase', 'model', 'api_mode')}, ensure_ascii=False))

    r1 = send_openai_compat(cfg, text_only_messages(api_mode), api_mode)
    print('text_only_http_status:', r1.status_code)
    print('text_only_body:', r1.text[:500])
    if r1.status_code >= 400:
        sys.exit(2)

    r2 = send_openai_compat(cfg, image_messages(api_mode), api_mode)
    print('image_http_status:', r2.status_code)
    print('image_body:', r2.text[:800])

    accepted = r2.status_code < 400
    print('image_supported:', accepted)
    if accepted:
        print('result: this endpoint appears to accept image input')
    else:
        print('result: this endpoint rejected image input or the model does not support it')


if __name__ == '__main__':
    main()
