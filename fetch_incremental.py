#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

API_BASE = "https://api.x.com/2"
ROOT = Path(__file__).resolve().parent
DEFAULT_WATCHLIST = ROOT / "watchlist.json"
DEFAULT_STATE = ROOT / "state.json"
DEFAULT_OUTPUT = ROOT / "data" / "latest_incremental.json"


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
        clean = {k: v for k, v in params.items() if v not in (None, "", [])}
        url = f"{url}?{urllib.parse.urlencode(clean)}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "x-digest-incremental/0.1")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        fail(f"HTTP {e.code} for {url}\n{body}")
    except Exception as e:
        fail(f"Request failed for {url}\n{e}")


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_username(raw: str) -> str:
    return raw.lstrip("@").strip()


def build_account_index(groups: Dict[str, List[str]], tags_by_account: Dict[str, List[str]]) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for group, accounts in groups.items():
        for raw in accounts:
            username = normalize_username(raw)
            if not username:
                continue
            item = merged.setdefault(username, {"username": username, "groups": set()})
            item["groups"].add(group)

    for raw, tags in tags_by_account.items():
        username = normalize_username(raw)
        if not username:
            continue
        item = merged.setdefault(username, {"username": username, "groups": set()})
        for tag in tags:
            item["groups"].add(tag)

    for item in merged.values():
        item["groups"] = sorted(item["groups"])

    return dict(sorted(merged.items()))


def get_user(username: str) -> Dict[str, Any]:
    data = api_get(f"/users/by/username/{urllib.parse.quote(username)}")
    if "data" not in data:
        fail(f"User lookup returned no data for @{username}:\n{json.dumps(data, ensure_ascii=False, indent=2)}")
    return data["data"]


def get_user_posts(user_id: str, since_id: str | None, max_results: int = 10) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    params = {
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics,conversation_id,referenced_tweets",
        "exclude": "replies",
        "since_id": since_id,
    }
    data = api_get(f"/users/{user_id}/tweets", params)
    return data.get("data", []), data.get("meta", {})


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


def main() -> None:
    watchlist_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_WATCHLIST
    state_path = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else DEFAULT_STATE
    output_path = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else DEFAULT_OUTPUT

    watchlist = load_json(watchlist_path, {"groups": {}, "tagsByAccount": {}})
    state = load_json(state_path, {"accounts": {}, "last_run_at": None})

    account_index = build_account_index(watchlist.get("groups", {}), watchlist.get("tagsByAccount", {}))
    now = datetime.now(timezone.utc).isoformat()

    results = []
    grouped_updates: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for username, meta in account_index.items():
        account_state = state["accounts"].get(username, {})
        user_id = account_state.get("user_id")
        if not user_id:
            user = get_user(username)
            user_id = user["id"]
            display_name = user.get("name")
        else:
            user = {"id": user_id, "username": username, "name": account_state.get("name")}
            display_name = account_state.get("name")

        since_id = account_state.get("since_id")
        posts, meta_resp = get_user_posts(user_id, since_id=since_id, max_results=10)
        normalized = normalize_posts(username, posts)

        newest_id = meta_resp.get("newest_id") or since_id
        state["accounts"][username] = {
            "user_id": user_id,
            "name": display_name,
            "since_id": newest_id,
            "last_checked_at": now,
            "groups": meta["groups"],
        }

        record = {
            "user": {
                "id": user_id,
                "name": display_name,
                "username": username,
            },
            "groups": meta["groups"],
            "new_posts_count": len(normalized),
            "new_posts": normalized,
        }
        results.append(record)

        if normalized:
            for group in meta["groups"]:
                grouped_updates[group].append(
                    {
                        "username": username,
                        "name": display_name,
                        "new_posts_count": len(normalized),
                        "new_posts": normalized,
                    }
                )

    state["last_run_at"] = now
    save_json(state_path, state)

    output = {
        "generated_at": now,
        "watchlist": str(watchlist_path),
        "state": str(state_path),
        "account_count": len(results),
        "accounts": results,
        "groups": grouped_updates,
    }
    save_json(output_path, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
