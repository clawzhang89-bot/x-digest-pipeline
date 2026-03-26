#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

API_BASE = "https://api.x.com/2"
ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = ROOT / "watchlist.seed.json"


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
        url = f"{url}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "x-digest-watchlist/0.1")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        fail(f"HTTP {e.code} for {url}\n{body}")
    except Exception as e:
        fail(f"Request failed for {url}\n{e}")


def load_watchlist(path: Path) -> Dict[str, Any]:
    if not path.exists():
        fail(f"Watchlist file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def normalize_posts(username: str, posts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for p in posts:
        out.append(
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
    return out


def build_account_index(groups: Dict[str, List[str]], tags_by_account: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for group, accounts in groups.items():
        for raw in accounts:
            username = raw.lstrip("@").strip()
            item = merged.setdefault(username, {"username": username, "groups": set()})
            item["groups"].add(group)

    for raw, tags in tags_by_account.items():
        username = raw.lstrip("@").strip()
        item = merged.setdefault(username, {"username": username, "groups": set()})
        for tag in tags:
            item["groups"].add(tag)

    for item in merged.values():
        item["groups"] = sorted(item["groups"])

    return dict(sorted(merged.items()))


def main() -> None:
    watchlist_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_WATCHLIST
    max_results = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    watchlist = load_watchlist(watchlist_path)
    groups = watchlist.get("groups", {})
    tags_by_account = watchlist.get("tagsByAccount", {})
    account_index = build_account_index(groups, tags_by_account)

    accounts_output = []
    posts_by_group: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for username, meta in account_index.items():
        user = get_user(username)
        posts = normalize_posts(username, get_user_posts(user["id"], max_results=max_results))
        account_record = {
            "user": {
                "id": user.get("id"),
                "name": user.get("name"),
                "username": user.get("username"),
            },
            "groups": meta["groups"],
            "posts": posts,
        }
        accounts_output.append(account_record)

        for group in meta["groups"]:
            posts_by_group[group].append(
                {
                    "username": user.get("username"),
                    "name": user.get("name"),
                    "posts": posts,
                }
            )

    result = {
        "watchlist": str(watchlist_path),
        "account_count": len(accounts_output),
        "accounts": accounts_output,
        "groups": posts_by_group,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
