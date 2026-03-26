#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "data" / "latest_incremental.json"
PLAN_PATH = ROOT / "data" / "topic_plan.json"
OUTPUT_ROOT = ROOT / "articles"
INDEX_PATH = OUTPUT_ROOT / "README.md"
JSON_INDEX_PATH = OUTPUT_ROOT / "index.json"

GROUP_TITLES = {
    "ai_llm": "AI / LLM",
    "embodied_vla_world_model": "具身智能 / VLA / 世界模型",
    "agents_automation": "Agent / 自动化 / Claude Code / OpenClaw",
}


def load_input(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing input file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_optional(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_", "/"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "untitled"


def summarize_group(group_key: str, items: List[Dict[str, Any]], mode: str = "new", series_title: str | None = None, previous_title: str | None = None) -> Dict[str, Any]:
    title = GROUP_TITLES.get(group_key, group_key)
    post_count = sum(item.get("new_posts_count", 0) for item in items)
    accounts = [item.get("username") for item in items]

    bullets = []
    source_section = []
    for item in items:
        username = item.get("username")
        name = item.get("name") or username
        posts = item.get("new_posts", [])[:3]
        if not posts:
            continue
        snippets = []
        for p in posts:
            text = (p.get("text") or "").replace("\n", " ").strip()
            if len(text) > 140:
                text = text[:140].rstrip() + "…"
            snippets.append(f"- {text} ({p.get('url')})")
        source_section.append(f"### @{username} / {name}\n" + "\n".join(snippets))
        bullets.append(f"{name}（@{username}）有 {len(posts)} 条值得关注的新内容。")

    if mode == "followup":
        article_title = f"{title}：延续上一篇讨论的新变化"
        lead = (
            f"这篇内容属于系列 follow-up。上一篇主要讨论的是《{previous_title or series_title or title}》，"
            f"这次新增材料继续围绕 {title} 展开，但重点在于新观点、新证据和新变化。"
        )
    else:
        article_title = f"{title}：今日值得关注的讨论与变化"
        lead = (
            f"今天这一组里一共出现了 {post_count} 条新内容，主要集中在 {title} 相关主题。"
            "当前版本先完成结构化整理与原始材料汇总，后续会在这里接入更强的主题归纳与记者式写作。"
        )

    body = [
        f"# {article_title}",
        "",
        f"生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 导语",
        lead,
        "",
        "## 本组今日动态",
    ]
    for b in bullets:
        body.append(f"- {b}")

    body.extend(
        [
            "",
            "## 值得后续成文的线索",
            "- 是否有多个账号在讨论同一个产品、发布或行业趋势。",
            "- 是否存在明显分歧：看多/看空、技术乐观/怀疑、平台机会/落地难点。",
            "- 是否需要补充背景信息，才能把零散帖子串成完整叙事。",
            "",
            "## 原始材料",
        ]
    )
    body.extend(source_section)

    return {
        "group": group_key,
        "title": article_title,
        "accounts": accounts,
        "post_count": post_count,
        "markdown": "\n".join(body).strip() + "\n",
    }


def write_articles(articles: List[Dict[str, Any]], generated_at: str, existing_index: Dict[str, Any]) -> List[Dict[str, Any]]:
    day = generated_at[:10]
    day_dir = OUTPUT_ROOT / day
    day_dir.mkdir(parents=True, exist_ok=True)

    written = []
    existing_articles = existing_index.get("articles", [])
    for idx, art in enumerate(articles, start=1):
        filename = f"{slugify(art['group'])}.md"
        path = day_dir / filename
        path.write_text(art["markdown"], encoding="utf-8")

        article_id = f"{day}-{slugify(art['group'])}-{idx}"
        source_post_ids = []
        for item in art.get("source_items", []):
            for p in item.get("new_posts", []):
                if p.get("id"):
                    source_post_ids.append(p["id"])

        entry = {
            "id": article_id,
            "date": day,
            "title": art["title"],
            "summary": art.get("summary", art["title"]),
            "tags": art.get("tags", []),
            "entities": art.get("entities", []),
            "group": art["group"],
            "series_id": art.get("series_id"),
            "series_title": art.get("series_title"),
            "is_followup": art.get("is_followup", False),
            "followup_to": art.get("followup_to"),
            "source_accounts": art["accounts"],
            "source_post_ids": source_post_ids,
            "path": str(path.relative_to(ROOT)),
        }
        existing_articles.append(entry)
        written.append(entry)

    existing_index["articles"] = existing_articles
    JSON_INDEX_PATH.write_text(json.dumps(existing_index, ensure_ascii=False, indent=2), encoding="utf-8")
    return written


def write_index(entries: List[Dict[str, Any]]) -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    lines = [
        "# X Digest Articles",
        "",
        "这个目录保存按天生成的文章原文，方便直接在 GitHub 查看。",
        "",
        "## 索引",
        "",
    ]

    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in entries:
        by_date[e["date"]].append(e)

    for date in sorted(by_date.keys(), reverse=True):
        lines.append(f"### {date}")
        for e in by_date[date]:
            accounts = ", ".join(f"@{a}" for a in e.get("source_accounts", [])[:8])
            lines.append(
                f"- [{e['title']}]({e['path']}) | group: `{e['group']}` | posts: {len(e.get('source_post_ids', []))} | accounts: {accounts}"
            )
        lines.append("")

    INDEX_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    data = load_input(INPUT_PATH)
    plan = load_optional(PLAN_PATH, {"plans": []})
    existing_index = load_optional(JSON_INDEX_PATH, {"articles": []})
    generated_at = data.get("generated_at") or datetime.now(timezone.utc).isoformat()

    articles = []
    if plan.get("plans"):
        for p in plan["plans"]:
            source_items = []
            for acc in p.get("account_summaries", []):
                source_items.append(
                    {
                        "username": acc.get("username"),
                        "name": acc.get("name"),
                        "new_posts_count": acc.get("post_count", 0),
                        "new_posts": acc.get("posts", []),
                    }
                )
            if not source_items:
                continue
            art = summarize_group(
                p.get("group", "mixed_updates"),
                source_items,
                mode=p.get("mode", "new"),
                series_title=p.get("series_title"),
                previous_title=p.get("series_title"),
            )
            art["is_followup"] = p.get("mode") == "followup"
            art["followup_to"] = p.get("followup_to")
            art["series_id"] = p.get("series_id") or (p.get("cluster_id") if p.get("mode") == "new" else None)
            art["series_title"] = p.get("series_title") or art["title"]
            art["tags"] = p.get("keywords", [])[:12]
            art["entities"] = p.get("entities", [])[:20]
            art["summary"] = art["title"]
            art["source_items"] = source_items
            articles.append(art)
    else:
        groups = data.get("groups", {})
        for group_key, items in groups.items():
            if not items:
                continue
            art = summarize_group(group_key, items)
            art["is_followup"] = False
            art["followup_to"] = None
            art["series_id"] = None
            art["series_title"] = art["title"]
            art["tags"] = []
            art["entities"] = []
            art["summary"] = art["title"]
            art["source_items"] = items
            articles.append(art)

    if not articles:
        print(json.dumps({"written": []}, ensure_ascii=False, indent=2))
        return

    entries = write_articles(articles, generated_at, existing_index)
    write_index(entries)
    print(json.dumps({"written": entries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
