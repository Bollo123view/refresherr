import os, urllib.parse

def build_find_link(base_url: str, token: str, link_type: str, term: str) -> str:
    q = urllib.parse.quote(term)
    if not base_url.endswith("/find"):
        base_url = base_url.rstrip("/") + "/find"
    return f"{base_url}?type={link_type}&term={q}&token={token}"

def relay_from_env(base_env: str, token_env: str) -> tuple[str,str]:
    return os.environ.get(base_env, ""), os.environ.get(token_env, "")
