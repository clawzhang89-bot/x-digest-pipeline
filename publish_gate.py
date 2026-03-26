#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "data" / "topic_plan.json"
INDEX_PATH = ROOT / "articles" / "index.json"
OUTPUT_PATH = ROOT / "data" / "publish_decisions.json"

MIN_NEW_POSTS_NEW = 3
MIN_NEW_POSTS_FOLLOWUP = 4
MIN_ACCOUNTS_FOLLOWUP = 2
LOOKBACK_ARTICLES = 12


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def recent_articles(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    return sorted(index.get("articles", []), key=lambda x: x.get("date", ""), reverse=True)[:LOOKBACK_ARTICLES]


def decide(plan: Dict[str, Any], index: Dict[str, Any]) -> Dict[str, Any]:
    account_summaries = plan.get("account_summaries", [])
    new_posts_total = sum(a.get("post_count", 0) for a in account_summaries)
    account_count = len([a for a in account_summaries if a.get("post_count", 0) > 0])
    mode = plan.get("mode", "new")

    decision = "publish"
    reason = ""

    if mode == "new":
        if new_posts_total < MIN_NEW_POSTS_NEW:
            decision = "skip"
            reason = f"new topic but too little material ({new_posts_total} posts)"
        else:
            reason = f"new topic with enough material ({new_posts_total} posts)"
    else:
        if new_posts_total < MIN_NEW_POSTS_FOLLOWUP:
            decision = "skip"
            reason = f"follow-up but too little new material ({new_posts_total} posts)"
        elif account_count < MIN_ACCOUNTS_FOLLOWUP:
            decision = "skip"
            reason = f"follow-up but not enough distinct accounts ({account_count})"
        else:
            reason = f"follow-up with sufficient new material ({new_posts_total} posts / {account_count} accounts)"

    if decision == "publish" and mode == "followup":
        followup_to = plan.get("followup_to")
        recent = recent_articles(index)
        if any(a.get("id") == followup_to and a.get("date") == datetime.now(timezone.utc).date().isoformat() for a in recent):
            decision = "skip"
            reason = "follow-up target already published today; avoid duplicate same-day output"

    return {
        "cluster_id": plan.get("cluster_id"),
        "group": plan.get("group"),
        "mode": mode,
        "accounts": plan.get("accounts", []),
        "new_posts_total": new_posts_total,
        "account_count": account_count,
        "decision": decision,
        "reason": reason,
        "followup_to": plan.get("followup_to"),
        "series_id": plan.get("series_id"),
    }


def main() -> None:
    plan_data = load_json(PLAN_PATH, {"plans": []})
    index = load_json(INDEX_PATH, {"articles": []})

    decisions = [decide(plan, index) for plan in plan_data.get("plans", [])]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decisions": decisions,
    }
    save_json(OUTPUT_PATH, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
