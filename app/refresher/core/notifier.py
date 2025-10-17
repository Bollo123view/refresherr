import os, json, requests

def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)

def discord_webhook_url_from_env(env_key: str) -> str:
    return _env(env_key, "")

def post_discord_simple(webhook: str, content: str) -> None:
    if not webhook:
        return
    try:
        requests.post(webhook, json={"content": content}, timeout=10).raise_for_status()
    except requests.RequestException:
        pass

def post_discord_file(webhook: str, filename: str, content: bytes, message: str = "") -> None:
    if not webhook:
        return
    files = {"file": (filename, content)}
    data = {"content": message} if message else {}
    try:
        requests.post(webhook, data=data, files=files, timeout=15).raise_for_status()
    except requests.RequestException:
        pass
