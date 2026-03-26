#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parent
INPUT_PATH = ROOT / "data" / "research_enrichment.json"
OUTPUT_PATH = ROOT / "data" / "research_materials.json"
ENV_PATH = ROOT / ".env.perplexity"
PPLX_SEARCH_URL = "https://api.perplexity.ai/search"
PPLX_SONAR_URL = "https://api.perplexity.ai/chat/completions"
DEFAULT_MAX_RESULTS = 8
DEFAULT_MAX_TOKENS_PER_PAGE = 768
SONAR_MODEL = "sonar"
MAX_EXEC_SUMMARY = 8
MAX_TIMELINE = 8
MAX_EVIDENCE_FOR = 6
MAX_EVIDENCE_AGAINST = 6
MAX_LANDSCAPE = 8
MAX_OPEN_QUESTIONS = 6
MAX_TEXT_LEN = 500
OFFICIAL_HINTS = [
    "github.com",
    "huggingface.co",
    "docs.",
    "blog.",
    "openai.com",
    "anthropic.com",
    "google.com",
    "deepmind.google",
    "perplexity.ai",
]
LOW_SIGNAL_HINTS = [
    "oschina.net",
    "jiemian.com",
    "36kr.com",
    "sohu.com",
    "163.com",
    "qq.com",
]


def load_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_env_key() -> Optional[str]:
    env_key = os.environ.get("PPLX_API_KEY")
    if env_key:
        return env_key.strip()
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "PPLX_API_KEY":
                return value.strip().strip('"').strip("'")
    return None


def clean_text(value: Any, max_len: int = MAX_TEXT_LEN) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u0000", " ").replace("\r", " ").replace("\n", " ").strip()
    text = " ".join(text.split())
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def clean_date(value: Any) -> str:
    text = clean_text(value, max_len=40)
    return text


def dedupe_strings(items: List[str], limit: int) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        txt = clean_text(item)
        if not txt or txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
        if len(out) >= limit:
            break
    return out


def build_perplexity_prompt(brief: Dict[str, Any]) -> str:
    lines = [
        "你是一个擅长技术与产业研究的研究员。",
        "请基于下面这篇 seed article 的研究 brief，产出一份 source-backed research pack。",
        "",
        "要求：",
        "1. 不要泛泛总结，要围绕给定问题逐条补证据。",
        "2. 优先使用官方博客、产品页、文档、GitHub、release notes、创始人/核心负责人公开表态。",
        "3. 可以使用高质量媒体或分析文章补背景，但请与一手来源区分开。",
        "4. 请明确区分：事实、判断、推演、未证实说法。",
        "5. 尽量补足时间线、反方观点、限制条件、行业位置。",
        "6. 输出需要足够支撑一篇 8~12 分钟中文技术时评。",
        "",
        f"主题：{brief.get('topic_title')}",
        f"核心论点：{brief.get('core_claim')}",
        f"涉及账号：{', '.join('@' + a for a in brief.get('accounts', []))}",
        f"关键实体：{', '.join(brief.get('entities', []))}",
        "",
        "当前 seed 的关键 claims：",
    ]
    for idx, claim in enumerate(brief.get("key_claims", []), start=1):
        lines.append(f"{idx}. {claim}")

    lines.extend(["", "当前文章薄弱点："])
    for idx, gap in enumerate(brief.get("content_gaps", []), start=1):
        lines.append(f"{idx}. {gap}")

    lines.extend(["", "请重点研究下面这些问题："])
    for idx, item in enumerate(brief.get("research_questions", []), start=1):
        lines.append(f"{idx}. [{item.get('dimension')}] {item.get('question')}")

    lines.extend([
        "",
        "请按以下结构输出：",
        "- executive_summary: 5-10 条要点",
        "- timeline: 按时间顺序列关键事件",
        "- evidence_for: 支持 seed 的证据",
        "- evidence_against: 反方/限制/反例",
        "- landscape: 关键公司、产品、路线图",
        "- sources: 每条 source 附 title/url/type/why_it_matters",
        "- unanswered_questions: 仍不确定的问题",
    ])
    return "\n".join(lines).strip() + "\n"


def build_sonar_messages(brief: Dict[str, Any]) -> List[Dict[str, str]]:
    system = (
        "你是一个技术媒体研究员。你的任务不是写文章，而是把 seed article 扩展成可供成文的 research pack。"
        "请优先引用官方博客、文档、GitHub、产品页和创始人/核心负责人公开表态。"
        "输出必须严格是 JSON，不要加 markdown 代码块。"
    )
    user = {
        "topic_title": brief.get("topic_title"),
        "core_claim": brief.get("core_claim"),
        "key_claims": brief.get("key_claims", []),
        "content_gaps": brief.get("content_gaps", []),
        "research_questions": brief.get("research_questions", []),
        "task": {
            "goal": "生成一份可供最终写作阶段消费的结构化 research pack",
            "output_schema": {
                "executive_summary": ["string"],
                "timeline": [{"date": "string", "event": "string", "why_it_matters": "string"}],
                "evidence_for": [{"claim": "string", "evidence": "string", "why_it_matters": "string"}],
                "evidence_against": [{"concern": "string", "evidence": "string", "why_it_matters": "string"}],
                "landscape": [{"name": "string", "role": "string", "why_it_matters": "string"}],
                "open_questions": ["string"]
            }
        }
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def search_queries_for_brief(brief: Dict[str, Any]) -> List[str]:
    queries: List[str] = []
    topic = brief.get("topic_title") or ""
    entities = brief.get("entities", [])[:4]
    core = brief.get("core_claim") or ""
    if topic:
        queries.append(topic)
    if core:
        queries.append(core)
    for item in brief.get("research_questions", [])[:6]:
        q = item.get("question")
        if q:
            queries.append(q)
    for ent in entities:
        queries.append(f"{ent} official blog")
        queries.append(f"{ent} GitHub release notes")
    deduped: List[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in deduped:
            deduped.append(q)
    return deduped[:8]


def perplexity_search(api_key: str, query: str) -> Dict[str, Any]:
    payload = {
        "query": query,
        "max_results": DEFAULT_MAX_RESULTS,
        "max_tokens_per_page": DEFAULT_MAX_TOKENS_PER_PAGE,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        PPLX_SEARCH_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text)


def perplexity_sonar(api_key: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
    payload = {
        "model": SONAR_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        PPLX_SONAR_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=90) as resp:
        text = resp.read().decode("utf-8")
        return json.loads(text)


def host_of(url: str) -> str:
    try:
        return parse.urlparse(url).netloc.lower()
    except Exception:
        return ""


def classify_source(url: str) -> str:
    host = host_of(url)
    if any(h in host for h in OFFICIAL_HINTS):
        return "official"
    if any(h in host for h in LOW_SIGNAL_HINTS):
        return "generic_media"
    if host:
        return "quality_media"
    return "unknown"


def compact_search_results(raw: Dict[str, Any], query: str) -> Dict[str, Any]:
    results = []
    for item in raw.get("results", []):
        url = item.get("url") or ""
        results.append({
            "title": clean_text(item.get("title")),
            "url": url,
            "host": host_of(url),
            "source_type": classify_source(url),
            "date": clean_date(item.get("date")),
            "last_updated": clean_date(item.get("last_updated")),
            "snippet": clean_text(item.get("snippet"), max_len=700),
            "query": clean_text(query),
        })
    return {
        "id": raw.get("id"),
        "query": clean_text(query),
        "results": results,
    }


def merge_results(search_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for run in search_runs:
        for item in run.get("results", []):
            url = item.get("url")
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(item)
    return merged


def safe_json_from_text(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def compact_sonar_response(raw: Dict[str, Any]) -> Dict[str, Any]:
    content = ((raw.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    parsed = None
    parse_error = None
    try:
        parsed = safe_json_from_text(content)
    except Exception as e:
        parse_error = f"{type(e).__name__}: {e}"
    search_results = []
    for item in raw.get("search_results", []) or []:
        url = item.get("url") or ""
        search_results.append({
            "title": clean_text(item.get("title")),
            "url": url,
            "host": host_of(url),
            "source_type": classify_source(url),
            "date": clean_date(item.get("date")),
            "last_updated": clean_date(item.get("last_updated")),
            "snippet": clean_text(item.get("snippet"), max_len=700),
        })
    return {
        "id": raw.get("id"),
        "model": raw.get("model"),
        "citations": raw.get("citations", []),
        "usage": raw.get("usage", {}),
        "content": content,
        "parsed": parsed,
        "parse_error": parse_error,
        "search_results": search_results,
    }


def normalize_summary(value: Any) -> List[str]:
    if isinstance(value, list):
        return dedupe_strings([clean_text(v) for v in value], MAX_EXEC_SUMMARY)
    if isinstance(value, str):
        lines = [x.strip(" -•") for x in value.split("\n") if x.strip()]
        if len(lines) <= 1:
            parts = [p.strip() for p in value.split("。") if p.strip()]
            return dedupe_strings(parts, MAX_EXEC_SUMMARY)
        return dedupe_strings(lines, MAX_EXEC_SUMMARY)
    return []


def normalize_object_list(value: Any, keys: List[str], limit: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen = set()
    if not isinstance(value, list):
        return out
    for item in value:
        if not isinstance(item, dict):
            continue
        obj = {k: clean_text(item.get(k)) for k in keys}
        signature = tuple(obj.get(k, "") for k in keys)
        if not any(signature):
            continue
        if signature in seen:
            continue
        seen.add(signature)
        out.append(obj)
        if len(out) >= limit:
            break
    return out


def normalize_open_questions(value: Any, fallback: List[str]) -> List[str]:
    items: List[str] = []
    if isinstance(value, list):
        items = [clean_text(v) for v in value]
    elif isinstance(value, str):
        items = [clean_text(x) for x in value.split("\n") if clean_text(x)]
    items = dedupe_strings(items, MAX_OPEN_QUESTIONS)
    if items:
        return items
    return dedupe_strings(fallback, MAX_OPEN_QUESTIONS)


def normalize_evidence_pack(brief: Dict[str, Any], sonar_data: Optional[Dict[str, Any]], merged_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    official = [r for r in merged_results if r.get("source_type") == "official"][:8]
    quality_media = [r for r in merged_results if r.get("source_type") == "quality_media"][:8]
    generic_media = [r for r in merged_results if r.get("source_type") == "generic_media"][:8]
    timeline_candidates = sorted(
        [r for r in merged_results if r.get("date")],
        key=lambda x: x.get("date") or "",
        reverse=True,
    )[:10]

    sonar_parsed = (sonar_data or {}).get("parsed") or {}
    citations = (sonar_data or {}).get("citations") or []

    executive_summary = normalize_summary(sonar_parsed.get("executive_summary"))
    timeline = normalize_object_list(sonar_parsed.get("timeline"), ["date", "event", "why_it_matters"], MAX_TIMELINE)
    evidence_for = normalize_object_list(sonar_parsed.get("evidence_for"), ["claim", "evidence", "why_it_matters"], MAX_EVIDENCE_FOR)
    evidence_against = normalize_object_list(sonar_parsed.get("evidence_against"), ["concern", "evidence", "why_it_matters"], MAX_EVIDENCE_AGAINST)
    landscape = normalize_object_list(sonar_parsed.get("landscape"), ["name", "role", "why_it_matters"], MAX_LANDSCAPE)
    open_questions = normalize_open_questions(sonar_parsed.get("open_questions"), brief.get("must_answer", []))

    if not evidence_for:
        for r in official[:5] + quality_media[:3]:
            evidence_for.append({
                "claim": clean_text(brief.get("core_claim")),
                "evidence": clean_text(r.get("snippet")),
                "why_it_matters": "候选支持证据，需在成文时进一步核对 claim 对应关系。",
            })
            if len(evidence_for) >= MAX_EVIDENCE_FOR:
                break

    if not evidence_against:
        evidence_against = [
            {
                "concern": "当前 source retrieval 仍可能受到搜索排序影响。",
                "evidence": "generic media 命中较多时，说明主题的高质量源还不够集中。",
                "why_it_matters": "避免把出现频率直接当成结论强度。",
            },
            {
                "concern": "反方材料可能不足。",
                "evidence": "当前结果未必系统覆盖失败案例、成本约束或 adoption 障碍。",
                "why_it_matters": "成文时应保留不确定性，不要写成单边叙事。",
            },
        ][:MAX_EVIDENCE_AGAINST]

    if not timeline:
        for r in timeline_candidates[:MAX_TIMELINE]:
            timeline.append({
                "date": clean_date(r.get("date") or r.get("last_updated")),
                "event": clean_text(r.get("title")),
                "why_it_matters": clean_text(r.get("snippet")),
            })

    if not landscape:
        seen = set()
        for r in official + quality_media:
            name = clean_text(r.get("title") or r.get("host"))
            role = clean_text(r.get("source_type") or "source")
            why = clean_text(r.get("snippet") or r.get("host"))
            sig = (name, role, why)
            if not name or sig in seen:
                continue
            seen.add(sig)
            landscape.append({"name": name, "role": role, "why_it_matters": why})
            if len(landscape) >= MAX_LANDSCAPE:
                break

    normalized = {
        "summary": {
            "total_sources": len(merged_results),
            "official_count": len(official),
            "quality_media_count": len(quality_media),
            "generic_media_count": len(generic_media),
            "sonar_citation_count": len(citations),
        },
        "source_buckets": {
            "official": official,
            "quality_media": quality_media,
            "generic_media": generic_media,
        },
        "executive_summary": executive_summary,
        "timeline": timeline[:MAX_TIMELINE],
        "timeline_candidates": timeline_candidates,
        "evidence_for": evidence_for[:MAX_EVIDENCE_FOR],
        "evidence_against": evidence_against[:MAX_EVIDENCE_AGAINST],
        "landscape": landscape[:MAX_LANDSCAPE],
        "open_questions": open_questions[:MAX_OPEN_QUESTIONS],
        "citations": citations[:20],
        "editorial_note": (
            "该 evidence pack 已经过 schema hardening：关键 section 已限长、去重、字段归一化。"
            "最终成文时，应优先使用 evidence_for / evidence_against / timeline / landscape，"
            "并把 source_buckets 作为回查来源池。"
        ),
    }
    return normalized


def collect_stub(brief: Dict[str, Any], api_key: Optional[str]) -> Dict[str, Any]:
    prompt = build_perplexity_prompt(brief)
    search_queries = search_queries_for_brief(brief)
    sonar_messages = build_sonar_messages(brief)
    perplexity_block: Dict[str, Any] = {
        "status": "prompt_ready",
        "prompt": prompt,
        "search_queries": search_queries,
        "results": None,
        "sonar": None,
    }
    evidence_pack = None

    if api_key:
        try:
            search_runs = []
            for query in search_queries[:5]:
                raw = perplexity_search(api_key, query)
                search_runs.append(compact_search_results(raw, query))
            merged_results = merge_results(search_runs)

            sonar_raw = perplexity_sonar(api_key, sonar_messages)
            sonar_data = compact_sonar_response(sonar_raw)

            evidence_pack = normalize_evidence_pack(brief, sonar_data, merged_results)
            perplexity_block["status"] = "results_ready"
            perplexity_block["results"] = {
                "search_runs": search_runs,
                "merged_results": merged_results,
            }
            perplexity_block["sonar"] = sonar_data
            perplexity_block["note"] = "Perplexity Search + Sonar 调用成功，已完成多 query 检索、source filtering、结构化 research summary 和 schema hardening。"
        except error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            perplexity_block["status"] = "error"
            perplexity_block["note"] = f"Perplexity API HTTPError: {e.code}"
            perplexity_block["error"] = body[:4000]
        except Exception as e:
            perplexity_block["status"] = "error"
            perplexity_block["note"] = f"Perplexity API error: {type(e).__name__}: {e}"
    else:
        perplexity_block["note"] = (
            "未发现 PPLX_API_KEY。当前仅生成适合发给 Perplexity 的 prompt / search queries / sonar messages，"
            "等配置 key 后再落真实 results。"
        )
        perplexity_block["sonar"] = {"messages": sonar_messages}

    return {
        "cluster_id": brief.get("cluster_id"),
        "group": brief.get("group"),
        "mode": brief.get("mode"),
        "topic_title": brief.get("topic_title"),
        "core_claim": brief.get("core_claim"),
        "research_goal": brief.get("research_goal"),
        "must_answer": brief.get("must_answer", []),
        "recommended_structure": brief.get("recommended_structure", []),
        "research_questions": brief.get("research_questions", []),
        "perplexity": perplexity_block,
        "evidence_pack": evidence_pack,
        "editorial_input": {
            "seed_posts": brief.get("seed_posts", []),
            "key_claims": brief.get("key_claims", []),
            "content_gaps": brief.get("content_gaps", []),
            "source_priority": brief.get("source_priority", []),
        },
        "notes": [
            "research 层现在同时使用 Search API 和 Sonar。",
            "Search API 提供 raw retrieval + source filtering；Sonar 提供结构化研究摘要和 citations。",
            "evidence pack 已经过 normalization / schema hardening，适合后续继续接审计 agent。",
        ],
    }


def main() -> None:
    data = load_json(INPUT_PATH, {"briefs": []})
    api_key = load_env_key()
    materials = [collect_stub(b, api_key) for b in data.get("briefs", [])]
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "materials": materials,
    }
    save_json(OUTPUT_PATH, output)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
