#!/usr/bin/env python3
"""
GitHub PR Summarizer — pipeline steps:

  fetch        GitHub → _detailed.csv
  summarize    _detailed.csv → _summarized.csv (per-PR ai_summary)
  technical    _detailed.csv → _technical_highlights.md
  by-project   _summarized.csv → _by_project.md
  perf-review  _summarized.csv → _perf_review.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

PROJECT_PATTERN = re.compile(r"\[[^\]]+\]\s*([^:]+):")


class PRSummarizer:

    def __init__(self):
        self.client = None
        self.model = None
        self._setup_anthropic()

    def _setup_anthropic(self):
        try:
            from anthropic import Anthropic

            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable required")
            self.client = Anthropic(api_key=api_key)
            self.model = os.getenv(
                "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
            )
            print(f"✅ Anthropic client initialized with model: {self.model}")
        except ImportError:
            print("❌ Anthropic library not installed. Run: pip install anthropic")
            sys.exit(1)

    def _call_llm(
        self,
        prompt: str,
        *,
        max_tokens: int = 150,
        system: str | None = None,
    ) -> str:
        system_content = system or (
            "You are a helpful assistant that summarizes GitHub pull requests "
            "concisely and accurately."
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_content,
                messages=[{"role": "user", "content": prompt}],
            )
            parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return "\n".join(parts).strip()
        except Exception as e:
            return f"Error: {e}"

    @staticmethod
    def extract_project_from_title(title: str) -> str:
        match = PROJECT_PATTERN.search(title)
        if match:
            return match.group(1).strip()
        return "Uncategorized"

    @staticmethod
    def group_prs_by_project(pr_data: List[Dict]) -> Dict[str, List[Dict]]:
        projects: Dict[str, List[Dict]] = defaultdict(list)
        for pr in pr_data:
            projects[PRSummarizer.extract_project_from_title(pr["title"])].append(pr)
        return dict(
            sorted(projects.items(), key=lambda item: len(item[1]), reverse=True)
        )

    def summarize_pr(self, title: str, description: str) -> str:
        prompt = f"""Summarize this GitHub pull request in 1-2 concise sentences. Focus on what was changed and why.

Title: {title}

Description: {description}

Summary:"""
        return self._call_llm(prompt)

    def analyze_pr_patterns(self, pr_data: List[Dict]) -> str:
        projects = self.group_prs_by_project(pr_data)

        project_breakdown = []
        for project, prs in projects.items():
            total_lines = sum(pr.get("lines_of_code_changes", 0) for pr in prs)
            project_breakdown.append(
                f"• {project}: {len(prs)} PRs, {total_lines} lines changed"
            )

        combined_summaries = "\n".join([
            f"• [{self.extract_project_from_title(pr['title'])}] "
            f"{pr.get('ai_summary', 'No summary')}"
            for pr in pr_data[:20]
        ])

        prompt = f"""Analyze these GitHub PR summaries and provide a comprehensive development activity report:

PROJECT BREAKDOWN:
{chr(10).join(project_breakdown)}

PR SUMMARIES BY PROJECT:
{combined_summaries}

Provide a detailed analysis covering:

1. **PROJECT FOCUS & IMPACT**
2. **TECHNICAL THEMES & PATTERNS**
3. **DEVELOPMENT VELOCITY & SCALE**
4. **CROSS-PROJECT INSIGHTS**
5. **KEY ACCOMPLISHMENTS & TRENDS**

Focus on actionable insights for performance reviews and project planning.

Analysis:"""

        return self._call_llm(prompt, max_tokens=800)

    def summarize_project_progress(self, project: str, prs: List[Dict]) -> str:
        pr_lines = []
        for pr in prs:
            desc = (pr.get("description") or "").strip()
            if not desc or desc == "No meaningful description available":
                desc = "(title only)"
            else:
                desc = desc[:400] + ("…" if len(desc) > 400 else "")
            summary = pr.get("ai_summary", "")
            if summary and summary != "No summary":
                desc = f"{desc}\n  Summary: {summary[:200]}"
            pr_lines.append(
                f"- {pr['title']} ({pr.get('lines_of_code_changes', 0)} lines)\n  {desc}"
            )

        prompt = f"""Summarize progress in this project area as 3–6 concise bullet points.
Focus on what shipped and the impact. Use markdown bullets (- ). No intro paragraph.

Project: {project}
PR count: {len(prs)}

PRs:
{chr(10).join(pr_lines)}

Progress bullets:"""

        return self._call_llm(
            prompt,
            max_tokens=350,
            system="You write concise engineering progress summaries grouped by project.",
        )

    def summarize_technical_highlight(
        self, title: str, description: str, pr_url: str
    ) -> Optional[str]:
        desc = (description or "").strip()
        if not desc or desc == "No meaningful description available":
            desc = "(no PR body — infer from title only if clearly technical)"

        prompt = f"""Review this pull request for interesting technical details worth sharing with senior engineers.

If there are NO substantive technical details (only trivial CSS tweaks, copy changes, config one-liners, or vague descriptions), respond with exactly:
SKIP

Otherwise write 2–4 concise bullet points on interesting technical work (architecture, algorithms, performance, infra, tricky bugs). No generic fluff. Do not repeat the title.

PR: {title}
URL: {pr_url}

Description:
{desc}

Technical bullets (or SKIP):"""

        result = self._call_llm(
            prompt,
            max_tokens=280,
            system=(
                "You highlight non-obvious technical implementation details in PRs. "
                "Skip routine or low-signal changes."
            ),
        )

        if not result or result.strip().upper() == "SKIP" or result.startswith("SKIP"):
            return None
        if "Error:" in result:
            return result
        return result

    def generate_by_project_report(self, pr_data: List[Dict]) -> str:
        projects = self.group_prs_by_project(pr_data)
        sections: List[str] = []

        for project, prs in projects.items():
            print(f"  • {project} ({len(prs)} PRs)...")
            bullets = self.summarize_project_progress(project, prs)
            sections.append(f"## {project}\n\n{bullets}\n")
            time.sleep(0.1)

        return "\n".join(sections)

    def generate_technical_report(self, pr_data: List[Dict]) -> str:
        sections: List[str] = []

        for idx, pr in enumerate(pr_data, 1):
            title = pr["title"]
            print(f"  [{idx}/{len(pr_data)}] {title[:60]}...")
            highlight = self.summarize_technical_highlight(
                title,
                pr.get("description", ""),
                pr.get("pr_url", ""),
            )
            if highlight:
                url = pr.get("pr_url", "")
                link = f"**[{title}]({url})**" if url else f"**{title}**"
                sections.append(f"### {link}\n\n{highlight}\n")
            time.sleep(0.1)

        if not sections:
            return "_No PRs with substantive technical details in this period._\n"

        return "\n---\n\n".join(sections) + "\n"


def date_part_from_path(path: str) -> str:
    base_name = os.path.basename(path)
    if base_name.startswith("pr_") and base_name.endswith(".csv"):
        date_part = base_name[3:-4]
        for suffix in ("_detailed", "_summarized"):
            if date_part.endswith(suffix):
                date_part = date_part[: -len(suffix)]
        return date_part
    return os.path.splitext(base_name)[0]


def paths_for_date_part(date_part: str) -> Dict[str, str]:
    prefix = f"output/pr_{date_part}"
    return {
        "detailed": f"{prefix}_detailed.csv",
        "summarized": f"{prefix}_summarized.csv",
        "by_project": f"{prefix}_by_project.md",
        "technical": f"{prefix}_technical_highlights.md",
        "perf_review": f"{prefix}_perf_review.md",
    }


def paths_from_detailed(detailed_csv: str) -> Dict[str, str]:
    return paths_for_date_part(date_part_from_path(detailed_csv))


def auto_detect_detailed_csv() -> str:
    output_dir = "output"
    if not os.path.exists(output_dir):
        raise FileNotFoundError("No output directory found. Run: python main.py fetch")

    csv_files = [
        f"{output_dir}/{f}"
        for f in os.listdir(output_dir)
        if f.startswith("pr_") and f.endswith("_detailed.csv")
    ]
    if not csv_files:
        raise FileNotFoundError(
            "No _detailed.csv found in output/. Run: python main.py fetch"
        )

    csv_files.sort(key=os.path.getmtime, reverse=True)
    return csv_files[0]


def csvs_ready(paths: Dict[str, str]) -> bool:
    return os.path.isfile(paths["detailed"]) and os.path.isfile(paths["summarized"])


def write_report_header(
    f, df: pd.DataFrame, date_part: str, *, title: str, subtitle: str
):
    date_range = date_part.replace("_", " – ")
    repo = os.getenv("GITHUB_REPO", "")

    f.write(f"# {title}\n\n")
    if repo:
        f.write(f"**Repo:** {repo}  \n")
    f.write(f"**Period:** {date_range}  \n")
    f.write(f"**Total PRs:** {len(df)}  \n")
    f.write(f"**Total Lines Changed:** {df['lines_of_code_changes'].sum():,}  \n")
    f.write(
        f"**Average Lines per PR:** {df['lines_of_code_changes'].mean():.1f}  \n\n"
    )
    f.write(f"{subtitle}\n\n")
    f.write("---\n\n")


def cmd_fetch(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> str:
    """Fetch PRs from GitHub → _detailed.csv."""
    if detailed_csv and os.path.isfile(detailed_csv):
        print(f"📂 Using existing detailed CSV: {detailed_csv}")
        return detailed_csv

    from github_pr_fetcher import main as fetch_prs

    print("📊 Fetching PRs from GitHub...")
    fetched = fetch_prs(start=start, end=end, days=days)
    if not fetched:
        raise RuntimeError("PR fetching failed")
    print(f"✅ PR data saved to: {fetched}")
    return fetched


def cmd_summarize(
    detailed_csv: str | None = None,
    *,
    force: bool = False,
) -> Tuple[str, str]:
    """Add per-PR ai_summary from _detailed.csv → _summarized.csv."""
    if not detailed_csv:
        detailed_csv = auto_detect_detailed_csv()
    paths = paths_from_detailed(detailed_csv)
    if not os.path.isfile(paths["detailed"]):
        raise FileNotFoundError(
            f"Detailed CSV not found: {paths['detailed']}. Run: python main.py fetch"
        )

    df = pd.read_csv(paths["detailed"])
    print(f"📊 Loaded {len(df)} PRs from {paths['detailed']}")

    if (
        not force
        and "ai_summary" in df.columns
        and df["ai_summary"].notna().all()
    ):
        print("ℹ️  Per-PR summaries already present; refreshing summarized CSV.")
    else:
        summarizer = PRSummarizer()
        print("🤖 Generating per-PR summaries...")
        summaries = []
        for idx, row in df.iterrows():
            print(f"  PR {idx + 1}/{len(df)}: {row['title'][:50]}...")
            summaries.append(summarizer.summarize_pr(row["title"], row["description"]))
            time.sleep(0.1)
        df = df.copy()
        df["ai_summary"] = summaries

    os.makedirs("output", exist_ok=True)
    df.to_csv(paths["summarized"], index=False)
    print(f"💾 Saved summarized data to {paths['summarized']}")

    return paths["detailed"], paths["summarized"]


def ensure_csvs(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> Dict[str, str]:
    """Ensure _detailed.csv and _summarized.csv exist; fetch and/or summarize as needed."""
    if detailed_csv:
        paths = paths_from_detailed(detailed_csv)
    else:
        try:
            detailed_csv = auto_detect_detailed_csv()
            paths = paths_from_detailed(detailed_csv)
        except FileNotFoundError:
            paths = None
            detailed_csv = None

    if paths and csvs_ready(paths):
        print(f"📂 Using {paths['detailed']}")
        return paths

    if paths and os.path.isfile(paths["detailed"]):
        print("⚠️  Missing _summarized.csv — running summarize...")
        cmd_summarize(paths["detailed"])
        return paths_from_detailed(paths["detailed"])

    detailed = cmd_fetch(detailed_csv, start=start, end=end, days=days)
    paths = paths_from_detailed(detailed)
    if not os.path.isfile(paths["summarized"]):
        cmd_summarize(detailed)
    return paths


def cmd_by_project(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> str:
    paths = ensure_csvs(detailed_csv, start=start, end=end, days=days)
    df = pd.read_csv(paths["summarized"])
    date_part = date_part_from_path(paths["summarized"])

    summarizer = PRSummarizer()
    print("📂 Summarizing by project area...")
    body = summarizer.generate_by_project_report(df.to_dict("records"))

    with open(paths["by_project"], "w") as f:
        write_report_header(
            f,
            df,
            date_part,
            title="PRs by Project Area",
            subtitle="*Progress summary per project area*",
        )
        f.write(body)

    print(f"📝 Saved report to {paths['by_project']}")
    return paths["by_project"]


def cmd_technical(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> str:
    paths = ensure_csvs(detailed_csv, start=start, end=end, days=days)
    df = pd.read_csv(paths["detailed"])
    date_part = date_part_from_path(paths["detailed"])

    summarizer = PRSummarizer()
    print("🔬 Extracting technical highlights...")
    body = summarizer.generate_technical_report(df.to_dict("records"))

    with open(paths["technical"], "w") as f:
        write_report_header(
            f,
            df,
            date_part,
            title="Technical Highlights",
            subtitle="*Interesting implementation details only*",
        )
        f.write(body)

    print(f"📝 Saved report to {paths['technical']}")
    return paths["technical"]


def cmd_perf_review(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> str:
    paths = ensure_csvs(detailed_csv, start=start, end=end, days=days)
    df = pd.read_csv(paths["summarized"])
    date_part = date_part_from_path(paths["summarized"])

    if "ai_summary" not in df.columns:
        raise ValueError("summarized CSV missing ai_summary; run: python main.py fetch")

    summarizer = PRSummarizer()
    print("🔍 Analyzing patterns for performance review...")
    pattern_analysis = summarizer.analyze_pr_patterns(df.to_dict("records"))

    with open(paths["perf_review"], "w") as f:
        write_report_header(
            f,
            df,
            date_part,
            title="GitHub PR Performance Review",
            subtitle="*Development activity analysis for performance reviews*",
        )
        f.write("## Development Activity Analysis\n\n")
        f.write(pattern_analysis)
        f.write("\n\n---\n\n## Individual PR Summaries\n\n")

        for idx, (_, row) in enumerate(df.iterrows()):
            project = summarizer.extract_project_from_title(row["title"])
            merged = row["merged"] is True or str(row["merged"]).lower() == "true"
            status_icon = "✅" if merged else "🔄" if row["state"] == "open" else "❌"

            f.write(f"### {idx + 1}. {row['title']}\n\n")
            f.write(f"**Project:** `{project}`  \n")
            f.write(
                f"**Lines Changed:** {row['lines_of_code_changes']} "
                f"(+{row['additions']}, -{row['deletions']})  \n"
            )
            f.write(f"**Status:** {row['state'].title()} {status_icon}  \n")
            f.write(f"**URL:** {row['pr_url']}\n\n")
            f.write(f"**Summary:** {row['ai_summary']}\n\n")
            f.write("---\n\n")

    print(f"📝 Saved report to {paths['perf_review']}")
    print("\n🎯 QUICK ANALYSIS")
    print("=" * 50)
    print(pattern_analysis)

    return paths["perf_review"]


def cmd_all(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
) -> str:
    """Fetch + all report types (including perf-review). Does not publish."""
    detailed = cmd_fetch(detailed_csv, start=start, end=end, days=days)
    cmd_summarize(detailed)
    cmd_by_project(detailed, start=start, end=end, days=days)
    cmd_technical(detailed, start=start, end=end, days=days)
    cmd_perf_review(detailed, start=start, end=end, days=days)
    return detailed


def cmd_publish(detailed_csv: str | None = None, *, push: bool = False) -> bool:
    """Copy output artifacts to pr-reports and commit."""
    from publish_reports import publish, prefix_from_csv

    if detailed_csv:
        prefix = prefix_from_csv(Path(detailed_csv))
    else:
        from publish_reports import latest_prefix

        prefix = latest_prefix()

    if not os.getenv("PR_REPORTS_DIR"):
        raise ValueError(
            "PR_REPORTS_DIR is not set in .env — required for publish"
        )

    print("📤 Publishing reports to pr-reports...")
    return publish(prefix, push=push)


def cmd_ship(
    detailed_csv: str | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    days: int | None = None,
    push: bool = False,
) -> str:
    """Fetch, by-project, technical, then publish to pr-reports."""
    detailed = cmd_fetch(detailed_csv, start=start, end=end, days=days)
    cmd_summarize(detailed)
    cmd_by_project(detailed, start=start, end=end, days=days)
    cmd_technical(detailed, start=start, end=end, days=days)
    cmd_publish(detailed, push=push)
    return detailed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="GitHub PR Analytics — fetch and generate reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""commands:
  fetch         GitHub → _detailed.csv
  summarize     _detailed.csv → _summarized.csv (Claude per-PR summaries)
  by-project    _summarized.csv → _by_project.md
  technical     _detailed.csv → _technical_highlights.md
  perf-review   _summarized.csv → _perf_review.md
  publish       Copy output/ to pr-reports repo and commit
  all           fetch + summarize + all reports
  ship          fetch + summarize + by-project + technical + publish (default)

Examples:
  python main.py fetch --start 2026-05-04 --end 2026-05-08
  python main.py summarize --csv output/pr_2026-05-04_2026-05-08_detailed.csv
  python main.py summarize --force
  python main.py ship --start 2026-05-04 --end 2026-05-08
  DAYS=7 python main.py fetch
  python main.py publish --push
""",
    )
    parser.add_argument(
        "--start",
        help="Start date YYYY-MM-DD, inclusive (or START_DATE env)",
    )
    parser.add_argument(
        "--end",
        help="End date YYYY-MM-DD, inclusive (or END_DATE env)",
    )
    parser.add_argument(
        "--days",
        type=int,
        help="Past N days from today (ignored if --start/--end set; default: DAYS env)",
    )
    parser.add_argument(
        "command",
        choices=[
            "fetch",
            "summarize",
            "by-project",
            "technical",
            "perf-review",
            "publish",
            "all",
            "ship",
        ],
        help="Pipeline step to run",
    )
    parser.add_argument(
        "--csv",
        dest="detailed_csv",
        help="Path to _detailed.csv (default: latest in output/)",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push pr-reports after commit (publish/ship only)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate all per-PR summaries (summarize only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    fetch_kw = {"start": args.start, "end": args.end, "days": args.days}

    try:
        if args.command == "fetch":
            detailed = cmd_fetch(args.detailed_csv, **fetch_kw)
            print(f"\n✅ Done: {detailed}")
        elif args.command == "summarize":
            detailed, summarized = cmd_summarize(
                args.detailed_csv, force=args.force
            )
            print(f"\n✅ Done: {detailed}\n           {summarized}")
        elif args.command == "by-project":
            out = cmd_by_project(args.detailed_csv, **fetch_kw)
            print(f"\n✅ Done: {out}")
        elif args.command == "technical":
            out = cmd_technical(args.detailed_csv, **fetch_kw)
            print(f"\n✅ Done: {out}")
        elif args.command == "perf-review":
            out = cmd_perf_review(args.detailed_csv, **fetch_kw)
            print(f"\n✅ Done: {out}")
        elif args.command == "publish":
            push = args.push or os.getenv("PUBLISH_PUSH", "").lower() in (
                "1",
                "true",
                "yes",
            )
            cmd_publish(args.detailed_csv, push=push)
            print("\n✅ Published to pr-reports")
        elif args.command == "all":
            cmd_all(args.detailed_csv, **fetch_kw)
            print("\n✅ All reports generated")
        elif args.command == "ship":
            push = args.push or os.getenv("PUBLISH_PUSH", "").lower() in (
                "1",
                "true",
                "yes",
            )
            cmd_ship(args.detailed_csv, push=push, **fetch_kw)
            print("\n✅ Shipped: reports generated and published")
        return 0
    except Exception as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
