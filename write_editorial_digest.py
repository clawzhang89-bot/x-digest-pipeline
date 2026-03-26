#!/usr/bin/env python3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "data" / "topic_plan.json"
DECISIONS_PATH = ROOT / "data" / "publish_decisions.json"
OUTPUT_ROOT = ROOT / "articles"
OUTBOX_PATH = ROOT / "editorial_requests"

GROUP_TITLES = {
    "ai_llm": "AI / LLM",
    "embodied_vla_world_model": "具身智能 / VLA / 世界模型",
    "agents_automation": "Agent / 自动化 / Claude Code / OpenClaw",
    "mixed_updates": "混合主题",
}

PROMPT_TEMPLATE = """你是一个技术媒体编辑。请根据下面材料，写一篇中文文章。

写作要求：
1. 不要机械复读原帖。
2. 要像记者一样整合多个博主的观点，提炼主线。
3. 如果这些材料与最近文章是同一主题的延续，请用 follow-up 的方式写，简单回顾前情，再重点写新增变化。
4. 如果多位博主在讨论同一个产品、发布、趋势或争议点，要把它们联动起来写，不要拆成流水账。
5. 要补足必要背景，但不要写成百科。
6. 文章要适合流畅阅读，并适合后续改编为播客口播稿。
7. 用中文写，冷静、直接、清楚，不要营销腔。
8. 时间线很重要。请优先按时间顺序理解材料，明确哪些观点是先出现的，哪些是后续补充、回应或推进；必要时在文中点出“几天前 / 今天 / 随后 / 本周”等时间关系。
9. 提到人名时，尽量补一个简短称谓或身份，帮助读者快速建立上下文，例如“OpenClaw 创始人 X”“投资人 Y”“播客主持人 Z”。称谓要克制、准确，不要乱封头衔。
10. 文章开头和结尾请加非常轻的问候语或收束语，让阅读更丝滑，但不要太客套、太肉麻、太像公众号模板。
11. 如果材料其实不足以支持一篇独立文章，请明确说明“NOT_ENOUGH_MATERIAL”。

请输出以下结构：
- title: 
- summary: （2~4句）
- tags: [最多8个]
- entities: [关键公司/产品/人物/概念]
- body_markdown: 正文 Markdown

主题组：{group_title}
模式：{mode}
系列标题：{series_title}
承接上一篇：{previous_title}
涉及账号：{accounts}
关键词：{keywords}
实体：{entities}

材料：
{materials}
"""


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def render_materials(account_summaries: List[Dict[str, Any]]) -> str:
    blocks = []
    for acc in account_summaries:
        header = f"## @{acc.get('username')} / {acc.get('name')}"
        posts = []
        for p in acc.get("posts", [])[:5]:
            text = (p.get("text") or "").strip()
            url = p.get("url") or ""
            created_at = p.get("created_at") or ""
            posts.append(f"- [{created_at}] {text}\n  {url}")
        blocks.append(header + "\n" + "\n".join(posts))
    return "\n\n".join(blocks)


def build_request(plan: Dict[str, Any]) -> Dict[str, Any]:
    group = plan.get("group", "mixed_updates")
    group_title = GROUP_TITLES.get(group, group)
    prompt = PROMPT_TEMPLATE.format(
        group_title=group_title,
        mode=plan.get("mode", "new"),
        series_title=plan.get("series_title") or "(none)",
        previous_title=plan.get("series_title") or "(none)",
        accounts=", ".join(f"@{a}" for a in plan.get("accounts", [])),
        keywords=", ".join(plan.get("keywords", [])[:20]),
        entities=", ".join(plan.get("entities", [])[:20]),
        materials=render_materials(plan.get("account_summaries", [])),
    )

    return {
        "cluster_id": plan.get("cluster_id"),
        "group": group,
        "mode": plan.get("mode", "new"),
        "series_id": plan.get("series_id"),
        "series_title": plan.get("series_title"),
        "followup_to": plan.get("followup_to"),
        "accounts": plan.get("accounts", []),
        "keywords": plan.get("keywords", []),
        "entities": plan.get("entities", []),
        "prompt": prompt,
    }


def write_requests(plans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    OUTBOX_PATH.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    written = []
    for idx, plan in enumerate(plans, start=1):
        req = build_request(plan)
        filename = f"{day}-{idx:02d}-{plan.get('group', 'topic')}.json"
        path = OUTBOX_PATH / filename
        path.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append({
            "cluster_id": plan.get("cluster_id"),
            "path": str(path.relative_to(ROOT)),
            "group": plan.get("group"),
            "mode": plan.get("mode"),
        })
    return written


def main() -> None:
    plan_data = load_json(PLAN_PATH, {"plans": []})
    decisions_data = load_json(DECISIONS_PATH, {"decisions": []})
    plans = plan_data.get("plans", [])
    decisions = {d.get("cluster_id"): d for d in decisions_data.get("decisions", [])}

    eligible = []
    for p in plans:
        d = decisions.get(p.get("cluster_id"))
        if d and d.get("decision") == "publish":
            eligible.append(p)

    if not eligible:
        print(json.dumps({"written": [], "skipped": len(plans)}, ensure_ascii=False, indent=2))
        return

    written = write_requests(eligible)
    print(json.dumps({"written": written, "skipped": len(plans) - len(eligible)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
