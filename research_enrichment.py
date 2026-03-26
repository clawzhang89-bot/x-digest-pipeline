#!/usr/bin/env python3
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent
PLAN_PATH = ROOT / "data" / "topic_plan.json"
OUTPUT_PATH = ROOT / "data" / "research_enrichment.json"
EDITORIAL_ROOT = ROOT / "editorial_requests"

SOURCE_PRIORITY = [
    "official_blog",
    "official_docs",
    "github_repo",
    "release_notes",
    "product_page",
    "official_statement",
    "x_search",
    "quality_media",
]

STOPWORDS = {
    "the", "this", "that", "these", "those", "with", "from", "into", "your", "our", "their",
    "today", "yesterday", "tomorrow", "will", "would", "could", "should", "about", "there", "here",
    "really", "actually", "almost", "around", "through", "after", "before", "because", "while",
    "agent", "agentic", "analysis", "architecture", "artificial", "chat", "business", "america",
    "american", "americans", "open", "fast", "faster", "live", "now", "our", "you", "here",
}

GROUP_ANGLE_HINTS = {
    "ai_llm": [
        "模型/产品这次到底发布了什么，和上一代相比新增了什么能力或定位？",
        "这个观点背后对应的真实产品变化、模型能力变化或基础设施变化是什么？",
        "如果把社交媒体上的兴奋情绪拿掉，真正值得写进文章的新增信息是什么？",
    ],
    "agents_automation": [
        "这波讨论指向的是模型能力变化，还是 agent workflow、tool reliability、eval、deployment 的变化？",
        "哪些公司或产品动作最能说明 agent 正在从 demo 走向实际 workflow？",
        "这类产品的主要分歧点是能力上限、可靠性、成本，还是采用门槛？",
    ],
    "embodied_vla_world_model": [
        "这波讨论到底是 research progress、demo 展示，还是接近产品化的信号？",
        "从模型、数据、仿真、硬件四个角度看，真正推动变化的变量是什么？",
        "哪些迹象说明这个方向在前进，哪些限制说明它还远没到规模落地？",
    ],
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


def latest_editorial_request(cluster_id: str) -> Dict[str, Any]:
    if not EDITORIAL_ROOT.exists():
        return {}
    matched = sorted(EDITORIAL_ROOT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in matched:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("cluster_id") == cluster_id:
            return data
    return {}


def strip_handles_and_urls(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"@\w+", " ", text)
    text = text.replace("RT ", " ")
    text = text.replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def first_sentence(text: str, max_len: int = 220) -> str:
    text = strip_handles_and_urls(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[。！？.!?])\s+|\n+", text)
    sentence = parts[0].strip() if parts else text.strip()
    if len(sentence) > max_len:
        sentence = sentence[:max_len].rstrip() + "…"
    return sentence


def normalize_entity(entity: str) -> str:
    entity = entity.strip()
    entity = entity.lstrip("@")
    entity = re.sub(r"[^A-Za-z0-9+._\-/ ]", "", entity)
    entity = re.sub(r"\s+", " ", entity).strip()
    return entity


def keep_entity(entity: str) -> bool:
    if not entity:
        return False
    low = entity.lower()
    if low in STOPWORDS:
        return False
    if len(entity) <= 2:
        return False
    if re.fullmatch(r"[A-Z]{1,4}", entity):
        return False
    if re.fullmatch(r"[A-Za-z]*\d{5,}[A-Za-z\d]*", entity):
        return False
    if entity.startswith("http"):
        return False
    return True


def top_entities(plan: Dict[str, Any]) -> List[str]:
    seen: List[str] = []
    for raw in plan.get("entities", []):
        ent = normalize_entity(str(raw))
        if keep_entity(ent) and ent not in seen:
            seen.append(ent)
    return seen[:8]


def extract_seed_posts(plan: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    for acc in plan.get("account_summaries", []):
        for p in acc.get("posts", [])[:limit]:
            text = (p.get("text") or "").strip()
            if not text:
                continue
            posts.append({
                "account": acc.get("username"),
                "name": acc.get("name"),
                "created_at": p.get("created_at"),
                "url": p.get("url"),
                "text": text,
                "summary": first_sentence(text),
            })
    posts.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return posts[:limit]


def infer_topic_title(plan: Dict[str, Any], entities: List[str], posts: List[Dict[str, Any]]) -> str:
    if entities:
        joined = " / ".join(entities[:3])
        return joined
    if posts:
        return first_sentence(posts[0]["text"], max_len=60)
    return plan.get("group", "topic")


def infer_core_claim(plan: Dict[str, Any], entities: List[str], posts: List[Dict[str, Any]]) -> str:
    group = plan.get("group")
    topic = infer_topic_title(plan, entities, posts)
    if group == "agents_automation":
        return f"围绕 {topic} 的讨论，核心不是单条帖子本身，而是 agent / automation 产品到底有没有进入更可用、更可靠的阶段。"
    if group == "ai_llm":
        return f"围绕 {topic} 的讨论，核心是这次模型/产品更新到底带来了什么真实变化，以及它是否足以支撑社交媒体上的叙事。"
    if group == "embodied_vla_world_model":
        return f"围绕 {topic} 的讨论，核心是这波进展到底意味着研究演示升级，还是距离产品化又近了一步。"
    return f"围绕 {topic} 的讨论，需要从零散观点里提炼出一个可验证的主判断。"


def infer_claims(plan: Dict[str, Any], entities: List[str], posts: List[Dict[str, Any]]) -> List[str]:
    claims: List[str] = []
    for post in posts[:3]:
        summary = post.get("summary")
        if summary and summary not in claims:
            claims.append(summary)
    if plan.get("group") == "agents_automation":
        defaults = [
            "这波讨论真正指向的瓶颈，可能不是模型本身，而是 workflow reliability、tool use、eval 或部署链路。",
            "如果多个账号都在讨论同类产品或能力，说明 agent/automation 正在从演示走向更具体的产品化阶段。",
        ]
    elif plan.get("group") == "ai_llm":
        defaults = [
            "社交媒体上的热度未必等于真实产品跃迁，需要回到官方发布和技术细节核验。",
            "如果这次更新真的重要，应该能从模型能力、产品定位、开发者反馈或基础设施变化里找到证据。",
        ]
    else:
        defaults = [
            "X 上的观点需要补足源头材料、时间线和反方限制，才能支撑更长的文章。",
            "真正值得写的，不是情绪最强的一句判断，而是背后那条更稳的事实链。",
        ]
    for item in defaults:
        if item not in claims:
            claims.append(item)
    return claims[:5]


def infer_gaps(plan: Dict[str, Any], entities: List[str]) -> List[str]:
    gaps = [
        "缺少把 seed 观点拆成可验证 claim 的过程，容易直接复述社交媒体叙事。",
        "缺少官方源头信息：产品页、博客、文档、发布说明、GitHub / release notes。",
        "缺少反方证据与现实限制，文章容易只站在一个情绪方向上。",
        "缺少时间线：为什么这件事是现在发生，而不是更早就成立。",
    ]
    if entities:
        gaps.append(f"缺少围绕 {', '.join(entities[:3])} 的行业位置判断：谁在推动，谁受益，谁仍然落后。")
    return gaps[:5]


def question_pack(plan: Dict[str, Any], entities: List[str], posts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[str]]:
    group = plan.get("group")
    horizon = "过去 12-24 个月"
    recent = "最近 3-6 个月"
    topic = infer_topic_title(plan, entities, posts)
    focus_entities = entities[:3] or [topic]
    ent_text = "、".join(focus_entities)

    questions = [
        {
            "dimension": "fact_check",
            "question": f"围绕 {ent_text} 的这篇 seed，最关键、最值得核验的 3-5 个 claim 分别是什么？请逐条给出支持或反驳证据，优先引用官方博客、产品文档、GitHub、发布说明或创始人/核心负责人原话。",
        },
        {
            "dimension": "timeline",
            "question": f"请梳理 {horizon} 内与 {ent_text} 相关的关键时间线，列出重要发布、模型/产品更新、融资、工程基础设施变化或行业转向，并说明为什么这些事件让今天这篇 seed 看起来成立。",
        },
        {
            "dimension": "supporting_evidence",
            "question": f"请找出最能支持这篇 seed 核心判断的 5-10 条证据，优先官方或高质量一手来源，并解释每条证据分别支持哪部分论点。",
        },
        {
            "dimension": "counterarguments",
            "question": f"这篇 seed 的叙事可能忽略了哪些反方观点、失败案例或现实限制？请从成本、可靠性、用户 adoption、工程复杂度、分发或商业化角度各找出至少一条。",
        },
        {
            "dimension": "landscape",
            "question": f"围绕 {ent_text}，当前主要玩家、产品路线或研究方向分别是什么？谁最积极推动这件事，谁会受益，谁的叙事可能被高估？",
        },
        {
            "dimension": "what_changed_now",
            "question": f"如果这篇 seed 不是空喊口号，那最近到底新增了什么？请重点说明 {recent} 内最关键的产品能力变化、模型变化、开发者体验变化或基础设施变化。",
        },
        {
            "dimension": "future_signals",
            "question": f"未来 3-6 个月，哪些可观测信号最能判断这篇 seed 的判断是否站得住？请给出具体指标、产品动作或市场信号。",
        },
    ]

    for hint in GROUP_ANGLE_HINTS.get(group, []):
        questions.append({"dimension": "group_specific", "question": hint})

    flat = [q["question"] for q in questions]
    return questions[:10], flat[:10]


def build_brief(plan: Dict[str, Any]) -> Dict[str, Any]:
    entities = top_entities(plan)
    posts = extract_seed_posts(plan)
    editorial = latest_editorial_request(plan.get("cluster_id", ""))
    topic_title = infer_topic_title(plan, entities, posts)
    core_claim = infer_core_claim(plan, entities, posts)
    key_claims = infer_claims(plan, entities, posts)
    content_gaps = infer_gaps(plan, entities)
    research_questions, suggested_queries = question_pack(plan, entities, posts)
    account_summaries = plan.get("account_summaries", [])
    post_count = sum(a.get("post_count", 0) for a in account_summaries)

    return {
        "cluster_id": plan.get("cluster_id"),
        "group": plan.get("group"),
        "mode": plan.get("mode"),
        "accounts": plan.get("accounts", []),
        "post_count": post_count,
        "keywords": plan.get("keywords", []),
        "entities": entities,
        "topic_title": topic_title,
        "core_claim": core_claim,
        "key_claims": key_claims,
        "content_gaps": content_gaps,
        "research_goal": "把 seed 文章扩展为 source-backed 的长文：先提炼高质量 research questions，再补足事实、背景、反方和行业位置，最后支撑 8~12 分钟口播级别文章。",
        "source_priority": SOURCE_PRIORITY,
        "must_answer": [
            "这篇 seed 真正想证明什么？",
            "哪些判断已经有证据，哪些还只是叙事？",
            "为什么这件事是现在发生，而不是更早就成立？",
            "最重要的反方和限制是什么？",
            "如果要扩成 10 分钟文章，最该补的是哪些事实和背景？",
        ],
        "recommended_structure": [
            "先明确 seed 的一句话论点",
            "补关键时间线与源头事实",
            "补最能支持论点的证据",
            "加入反方、限制与未解决问题",
            "最后收束到行业判断和后续观察点",
        ],
        "seed_posts": posts,
        "editorial_prompt_excerpt": (editorial.get("prompt") or "")[:1200],
        "research_questions": research_questions,
        "suggested_queries": suggested_queries,
    }


def main() -> None:
    plan_data = load_json(PLAN_PATH, {"plans": []})
    briefs = [build_brief(p) for p in plan_data.get("plans", [])]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "briefs": briefs,
    }
    save_json(OUTPUT_PATH, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
