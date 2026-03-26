#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List

API_BASE = "https://api.x.com/2"


def fail(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def get_bearer_token() -> str:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        fail("Missing X_BEARER_TOKEN in environment.")
    return token


def api_get(path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
    token = get_bearer_token()
    url = f"{API_BASE}{path}"
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "x-digest-test/0.1")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        fail(f"HTTP {e.code} for {url}\n{body}")
    except Exception as e:
        fail(f"Request failed for {url}\n{e}")


def get_user(username: str) -> Dict[str, Any]:
    data = api_get(f"/users/by/username/{urllib.parse.quote(username)}")
    if "data" not in data:
        fail(f"User lookup returned no data for @{username}:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
    return data["data"]


def get_user_posts(user_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
    data = api_get(
        f"/users/{user_id}/tweets",
        {
            "max_results": max_results,
            "tweet.fields": "created_at,public_metrics,conversation_id,referenced_tweets",
            "exclude": "replies",
        },
    )
    return data.get("data", [])


def normalize_posts(username: str, user: Dict[str, Any], posts: List[Dict[str, Any]]) -> Dict[str, Any]:
    normalized = []
    for p in posts:
        normalized.append(
            {
                "id": p.get("id"),
                "created_at": p.get("created_at"),
                "text": p.get("text"),
                "url": f"https://x.com/{username}/status/{p.get('id')}",
                "conversation_id": p.get("conversation_id"),
                "referenced_tweets": p.get("referenced_tweets", []),
                "public_metrics": p.get("public_metrics", {}),
            }
        )

    return {
        "user": {
            "id": user.get("id"),
            "name": user.get("name"),
            "username": user.get("username"),
        },
        "posts": normalized,
    }


def main() -> None:
    usernames = sys.argv[1:]
    if not usernames:
        fail("Usage: python3 fetch_test.py <username> [username2 ...]")

    results = []
    for raw in usernames:
        username = raw.lstrip("@").strip()
        user = get_user(username)
        posts = get_user_posts(user["id"], max_results=5)
        results.append(normalize_posts(username, user, posts))

    print(json.dumps({"accounts": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
