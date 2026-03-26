#!/usr/bin/env python3
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set

ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "data" / "latest_incremental.json"
ARTICLE_INDEX = ROOT / "articles" / "index.json"
OUTPUT_PATH = ROOT / "data" / "topic_plan.json"

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "your", "their",
    "今天", "一个", "我们", "他们", "这个", "那个", "以及", "相关", "正在", "已经", "可以", "没有",
    "agent", "agents", "llm", "ai"
}


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def tokenize(text: str) -> Set[str]:
    words = re.findall(r"[A-Za-z0-9_\-\u4e00-\u9fff]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def extract_entities(posts: List[Dict[str, Any]]) -> List[str]:
    entities = set()
    for p in posts:
        text = p.get("text", "")
        for token in re.findall(r"@[A-Za-z0-9_]+|[A-Z][A-Za-z0-9_\-]{2,}", text):
            entities.add(token.strip())
    return sorted(entities)


def summarize_account(acc: Dict[str, Any]) -> Dict[str, Any]:
    posts = acc.get("new_posts", [])
    text_blob = "\n".join(p.get("text", "") for p in posts)
    keywords = sorted(list(tokenize(text_blob)))[:12]
    entities = extract_entities(posts)
    return {
        "username": acc["user"]["username"],
        "name": acc["user"].get("name"),
        "groups": acc.get("groups", []),
        "post_count": acc.get("new_posts_count", 0),
        "keywords": keywords,
        "entities": entities,
        "posts": posts,
    }


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_related_article(cluster_keywords: Set[str], cluster_entities: Set[str], recent_articles: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    best = None
    best_score = 0.0
    for art in recent_articles:
        art_tokens = set(art.get("tags", [])) | set(art.get("entities", [])) | tokenize(art.get("title", "") + " " + art.get("summary", ""))
        score = max(jaccard(cluster_keywords, art_tokens), jaccard(cluster_entities, art_tokens))
        if score > best_score:
            best_score = score
            best = art
    if best_score >= 0.18:
        return best
    return None


def cluster_accounts(accounts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for acc in accounts:
        primary_group = acc.get("groups", ["mixed"])[0] if acc.get("groups") else "mixed"
        grouped[primary_group].append(acc)

    clusters = []
    for group, items in grouped.items():
        all_keywords = set()
        all_entities = set()
        for item in items:
            all_keywords |= set(item.get("keywords", []))
            all_entities |= set(item.get("entities", []))
        clusters.append(
            {
                "cluster_id": f"{group}-{len(items)}",
                "group": group,
                "accounts": items,
                "keywords": sorted(all_keywords),
                "entities": sorted(all_entities),
            }
        )
    return clusters


def main() -> None:
    data = load_json(INPUT_PATH, {})
    index = load_json(ARTICLE_INDEX, {"articles": []})

    recent_articles = sorted(index.get("articles", []), key=lambda x: x.get("date", ""), reverse=True)[:12]
    accounts = [summarize_account(acc) for acc in data.get("accounts", []) if acc.get("new_posts_count", 0) > 0]
    clusters = cluster_accounts(accounts)

    plans = []
    for cl in clusters:
        kw = set(cl.get("keywords", []))
        ent = set(cl.get("entities", []))
        related = find_related_article(kw, ent, recent_articles)

        mode = "new"
        followup_to = None
        series_id = None
        series_title = None
        if related:
            mode = "followup"
            followup_to = related.get("id")
            series_id = related.get("series_id") or related.get("id")
            series_title = related.get("series_title") or related.get("title")

        plans.append(
            {
                "cluster_id": cl["cluster_id"],
                "group": cl["group"],
                "mode": mode,
                "followup_to": followup_to,
                "series_id": series_id,
                "series_title": series_title,
                "accounts": [a["username"] for a in cl["accounts"]],
                "keywords": cl["keywords"],
                "entities": cl["entities"],
                "account_summaries": [
                    {
                        "username": a["username"],
                        "name": a["name"],
                        "groups": a["groups"],
                        "post_count": a["post_count"],
                        "keywords": a["keywords"],
                        "entities": a["entities"],
                        "posts": a["posts"],
                    }
                    for a in cl["accounts"]
                ],
            }
        )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "plans": plans,
    }
    save_json(OUTPUT_PATH, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
