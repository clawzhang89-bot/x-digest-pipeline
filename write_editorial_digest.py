#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "data" / "topic_plan.json"
DECISIONS_PATH = ROOT / "data" / "publish_decisions.json"
RESEARCH_MATERIALS_PATH = ROOT / "data" / "research_materials.json"
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
10. 这是为播客改编准备的文章。文章开头和结尾请加非常轻的问候语或收束语，让阅读和口播更丝滑，但不要太客套、太肉麻、太像公众号模板。
11. 正文开头的第一句，请先用自然口播方式重复一次标题，例如：`今天我们要聊的话题是：“XXX”。` 然后再进入导语和正文。
12. 如果有 research pack，请优先把其中已经核验过的事实、时间线、反方观点和行业格局吃进去；不要只围绕 seed 原帖写。
13. 如果 evidence pack 已经提供了 `timeline` / `evidence_for` / `evidence_against` / `landscape` / `open_questions`，正文应优先消费这些结构化材料，而不是只摘取 `source_buckets` 或原始 seed。
14. 如果 research pack 里还没有真实来源结果，请把它当成写作约束与补充角度，而不是假装已经有了外部证据。
15. 如果材料其实不足以支持一篇独立文章，请明确说明“NOT_ENOUGH_MATERIAL”。

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

seed 材料：
{materials}

research pack：
{research_pack}
"""


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def render_research_pack(material: Dict[str, Any]) -> str:
    if not material:
        return "(none)"

    lines = [
        f"topic_title: {material.get('topic_title')}",
        f"core_claim: {material.get('core_claim')}",
        f"research_goal: {material.get('research_goal')}",
        "",
        "must_answer:",
    ]
    for item in material.get("must_answer", []):
        lines.append(f"- {item}")

    lines.extend(["", "recommended_structure:"])
    for item in material.get("recommended_structure", []):
        lines.append(f"- {item}")

    lines.extend(["", "key_claims:"])
    for item in material.get("editorial_input", {}).get("key_claims", []):
        lines.append(f"- {item}")

    lines.extend(["", "content_gaps:"])
    for item in material.get("editorial_input", {}).get("content_gaps", []):
        lines.append(f"- {item}")

    lines.extend(["", "research_questions:"])
    for item in material.get("research_questions", []):
        lines.append(f"- [{item.get('dimension')}] {item.get('question')}")

    pplx = material.get("perplexity", {})
    lines.extend(["", f"perplexity_status: {pplx.get('status', 'unknown')}"])
    if pplx.get("note"):
        lines.append(f"perplexity_note: {pplx.get('note')}")

    evidence_pack = material.get("evidence_pack")
    if evidence_pack:
        lines.extend(["", "evidence_pack:"])
        lines.append(json.dumps(evidence_pack, ensure_ascii=False, indent=2))

    results = pplx.get("results")
    if results:
        lines.extend(["", "perplexity_results:"])
        if isinstance(results, str):
            lines.append(results)
        else:
            lines.append(json.dumps(results, ensure_ascii=False, indent=2)[:5000])
    else:
        prompt = pplx.get("prompt") or ""
        if prompt:
            lines.extend(["", "perplexity_prompt_preview:"])
            lines.append(prompt[:3000])

    return "\n".join(lines).strip() + "\n"


def build_request(plan: Dict[str, Any], research_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    group = plan.get("group", "mixed_updates")
    group_title = GROUP_TITLES.get(group, group)
    material = research_map.get(plan.get("cluster_id"), {})
    research_pack = render_research_pack(material)
    prompt = PROMPT_TEMPLATE.format(
        group_title=group_title,
        mode=plan.get("mode", "new"),
        series_title=plan.get("series_title") or "(none)",
        previous_title=plan.get("series_title") or "(none)",
        accounts=", ".join(f"@{a}" for a in plan.get("accounts", [])),
        keywords=", ".join(plan.get("keywords", [])[:20]),
        entities=", ".join(plan.get("entities", [])[:20]),
        materials=render_materials(plan.get("account_summaries", [])),
        research_pack=research_pack,
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
        "research_material": material,
        "prompt": prompt,
    }


def write_requests(plans: List[Dict[str, Any]], research_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    OUTBOX_PATH.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).date().isoformat()
    written = []
    for idx, plan in enumerate(plans, start=1):
        req = build_request(plan, research_map)
        filename = f"{day}-{idx:02d}-{plan.get('group', 'topic')}.json"
        path = OUTBOX_PATH / filename
        path.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append({
            "cluster_id": plan.get("cluster_id"),
            "path": str(path.relative_to(ROOT)),
            "group": plan.get("group"),
            "mode": plan.get("mode"),
            "has_research_material": bool(req.get("research_material")),
        })
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Write editorial requests for x-digest")
    parser.add_argument("--all-plans", action="store_true", help="Write requests for all topic plans, ignoring publish decisions")
    args = parser.parse_args()

    plan_data = load_json(PLAN_PATH, {"plans": []})
    decisions_data = load_json(DECISIONS_PATH, {"decisions": []})
    research_data = load_json(RESEARCH_MATERIALS_PATH, {"materials": []})

    plans = plan_data.get("plans", [])
    decisions = {d.get("cluster_id"): d for d in decisions_data.get("decisions", [])}
    research_map = {m.get("cluster_id"): m for m in research_data.get("materials", [])}

    if args.all_plans:
        eligible = plans
    else:
        eligible = []
        for p in plans:
            d = decisions.get(p.get("cluster_id"))
            if d and d.get("decision") == "publish":
                eligible.append(p)

    if not eligible:
        print(json.dumps({"written": [], "skipped": len(plans)}, ensure_ascii=False, indent=2))
        return

    written = write_requests(eligible, research_map)
    print(json.dumps({
        "written": written,
        "skipped": max(len(plans) - len(eligible), 0),
        "used_all_plans": args.all_plans,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
