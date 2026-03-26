#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WATCHLIST_DEFAULT = ROOT / "watchlist.json"
STATE_DEFAULT = ROOT / "state.json"
INCREMENTAL_DEFAULT = ROOT / "data" / "latest_incremental.json"
PLAN_DEFAULT = ROOT / "data" / "topic_plan.json"
DECISIONS_DEFAULT = ROOT / "data" / "publish_decisions.json"
RESEARCH_ENRICHMENT_DEFAULT = ROOT / "data" / "research_enrichment.json"
RESEARCH_MATERIALS_DEFAULT = ROOT / "data" / "research_materials.json"
REPORTS_DIR = ROOT / "reports"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(cwd or ROOT))
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def render_report(plan: dict, decisions: dict) -> str:
    plans = {p.get('cluster_id'): p for p in plan.get('plans', [])}
    rows = decisions.get('decisions', [])
    lines = ["# Digest Report", ""]
    if not rows:
        lines.append("No planned topics.")
        return "\n".join(lines) + "\n"

    publish_rows = [r for r in rows if r.get('decision') == 'publish']
    skip_rows = [r for r in rows if r.get('decision') != 'publish']
    lines.append(f"summary: {len(rows)} topic(s) | publish={len(publish_rows)} | skip={len(skip_rows)}")
    lines.append("")

    if publish_rows:
        lines.append("## To publish")
        lines.append("")
        for row in publish_rows:
            cid = row.get('cluster_id')
            p = plans.get(cid, {})
            accounts = ", ".join(f"@{a}" for a in row.get('accounts', [])) or "(none)"
            keywords = ", ".join(p.get('keywords', [])[:6])
            lines.append(f"- **[{row.get('group')}] {cid}** | {row.get('mode')} | posts={row.get('new_posts_total')} | accounts={accounts}")
            if keywords:
                lines.append(f"  - keywords: {keywords}")
            lines.append(f"  - reason: {row.get('reason')}")
        lines.append("")

    if skip_rows:
        lines.append("## Skipped")
        lines.append("")
        for row in skip_rows:
            cid = row.get('cluster_id')
            p = plans.get(cid, {})
            accounts = ", ".join(f"@{a}" for a in row.get('accounts', [])) or "(none)"
            keywords = ", ".join(p.get('keywords', [])[:6])
            lines.append(f"- **[{row.get('group')}] {cid}** | {row.get('mode')} | posts={row.get('new_posts_total')} | accounts={accounts}")
            lines.append(f"  - reason: {row.get('reason')}")
            if keywords:
                lines.append(f"  - keywords: {keywords}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def print_report(plan: dict, decisions: dict) -> None:
    print("\n" + render_report(plan, decisions))


def write_report(plan: dict, decisions: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report = render_report(plan, decisions)
    date = decisions.get('generated_at', '')[:10] or 'latest'
    dated = REPORTS_DIR / f"{date}.md"
    latest = REPORTS_DIR / "latest.md"
    dated.write_text(report, encoding='utf-8')
    latest.write_text(report, encoding='utf-8')
    return dated


def main() -> None:
    parser = argparse.ArgumentParser(description="Run x-digest pipeline")
    parser.add_argument("--watchlist", default=str(WATCHLIST_DEFAULT), help="Path to watchlist json")
    parser.add_argument("--state", default=str(STATE_DEFAULT), help="Path to state json")
    parser.add_argument("--incremental", default=str(INCREMENTAL_DEFAULT), help="Path to incremental output json")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetch_incremental")
    parser.add_argument("--skip-plan", action="store_true", help="Skip topic planning")
    parser.add_argument("--skip-gate", action="store_true", help="Skip publish gate")
    parser.add_argument("--skip-request", action="store_true", help="Skip editorial request generation")
    parser.add_argument("--skip-research", action="store_true", help="Skip research enrichment + collection")
    parser.add_argument("--skip-generate", action="store_true", help="Skip markdown article generation")
    parser.add_argument("--report-only", action="store_true", help="Run planning + gate only, then print report and stop")
    args = parser.parse_args()

    watchlist = str(Path(args.watchlist).resolve())
    state = str(Path(args.state).resolve())
    incremental = str(Path(args.incremental).resolve())

    if not args.skip_fetch:
        run([sys.executable, "fetch_incremental.py", watchlist, state, incremental], cwd=ROOT)

    if not args.skip_plan:
        run([sys.executable, "topic_planner.py"], cwd=ROOT)

    if not args.skip_gate:
        run([sys.executable, "publish_gate.py"], cwd=ROOT)

    if args.report_only:
        plan = load_json(PLAN_DEFAULT, {"plans": []})
        decisions = load_json(DECISIONS_DEFAULT, {"decisions": []})
        report_path = write_report(plan, decisions)
        print_report(plan, decisions)
        print(f"Report saved to: {report_path}")
        print(f"Latest report: {REPORTS_DIR / 'latest.md'}")
        print("\nReport-only mode complete.")
        return

    if not args.skip_request:
        run([sys.executable, "write_editorial_digest.py"], cwd=ROOT)

    if not args.skip_research:
        run([sys.executable, "research_enrichment.py"], cwd=ROOT)
        run([sys.executable, "research_collect.py"], cwd=ROOT)

    if not args.skip_generate:
        run([sys.executable, "generate_digest.py"], cwd=ROOT)

    plan = load_json(PLAN_DEFAULT, {"plans": []})
    print("\nPipeline complete.")
    print(f"Planned topics: {len(plan.get('plans', []))}")
    print("Outputs:")
    print(f"- Incremental data: {incremental}")
    print(f"- Topic plan: {PLAN_DEFAULT}")
    print(f"- Publish decisions: {ROOT / 'data' / 'publish_decisions.json'}")
    print(f"- Editorial requests: {ROOT / 'editorial_requests'}")
    print(f"- Research enrichment: {RESEARCH_ENRICHMENT_DEFAULT}")
    print(f"- Research materials: {RESEARCH_MATERIALS_DEFAULT}")
    print(f"- Articles index: {ROOT / 'articles' / 'README.md'}")
    print(f"- Articles metadata: {ROOT / 'articles' / 'index.json'}")


if __name__ == "__main__":
    main()
