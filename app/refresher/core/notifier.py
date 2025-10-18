import os, requests
def post_discord(content: str, webhook: str | None = None) -> bool:
    url = webhook or os.getenv("DISCORD_WEBHOOK", "")
    if not url: 
        print("No DISCORD_WEBHOOK"); 
        return False
    try:
        r = requests.post(url, json={"content": content}, timeout=10)
        print("Discord response:", r.status_code)
        return r.ok
    except Exception as e:
        print("Discord error:", e)
        return False
