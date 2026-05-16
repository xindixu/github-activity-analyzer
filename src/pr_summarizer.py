#!/usr/bin/env python3
"""
GitHub PR Summarizer — three report modes:

  perf-review   Performance-review report (per-PR summaries + pattern analysis)
  by-project    Group PRs by project area with concise progress bullets
  technical     Highlight interesting technical details; skip uninteresting PRs
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

SUMMARIZE_MODES = ("perf-review", "by-project", "technical")
DEFAULT_MODE = "perf-review"

PROJECT_PATTERN = re.compile(r"\[[^\]]+\]\s*([^:]+):")


class PRSummarizer:

    def __init__(self):
        self.client = None
        self.model = None
        self._setup_openai()

    def _setup_openai(self):
        try:
            import openai

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable required")
            self.client = openai.OpenAI(api_key=api_key)
            self.model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
            print(f"✅ OpenAI client initialized with model: {self.model}")
        except ImportError:
            print("❌ OpenAI library not installed. Run: pip install openai")
            sys.exit(1)

    def _call_openai(
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
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"

    @staticmethod
    def extract_project_from_title(title: str) -> str:
        """Extract project from titles like `feat: [SUP-1] Storybook: ...`."""
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
        return self._call_openai(prompt)

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

        return self._call_openai(prompt, max_tokens=800)

    def summarize_project_progress(
        self, project: str, prs: List[Dict]
    ) -> str:
        pr_lines = []
        for pr in prs:
            desc = (pr.get("description") or "").strip()
            if not desc or desc == "No meaningful description available":
                desc = "(title only)"
            else:
                desc = desc[:400] + ("…" if len(desc) > 400 else "")
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

        return self._call_openai(
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

        result = self._call_openai(
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


def resolve_mode(mode: str | None = None) -> str:
    chosen = (mode or os.getenv("SUMMARIZE_MODE", DEFAULT_MODE)).strip().lower()
    if chosen not in SUMMARIZE_MODES:
        raise ValueError(
            f"Invalid mode '{chosen}'. Choose from: {', '.join(SUMMARIZE_MODES)}"
        )
    return chosen


def date_part_from_csv(csv_file: str) -> str:
    base_name = os.path.basename(csv_file)
    if base_name.startswith("pr_") and base_name.endswith(".csv"):
        date_part = base_name[3:-4]
        if date_part.endswith("_detailed"):
            date_part = date_part[: -len("_detailed")]
        return date_part
    return os.path.splitext(base_name)[0]


def report_paths(csv_file: str, mode: str) -> tuple[str, str]:
    """Return (summarized_csv_path or None, markdown_report_path)."""
    date_part = date_part_from_csv(csv_file)
    prefix = f"output/pr_{date_part}"

    if mode == "perf-review":
        return f"{prefix}_summarized.csv", f"{prefix}_summary.md"
    if mode == "by-project":
        return None, f"{prefix}_by_project.md"
    return None, f"{prefix}_technical_highlights.md"


def write_report_header(f, df: pd.DataFrame, csv_file: str, *, title: str, subtitle: str):
    date_part = date_part_from_csv(csv_file)
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


def process_perf_review(
    summarizer: PRSummarizer, df: pd.DataFrame, csv_file: str, output_file: str | None
) -> str:
    summarized_csv, analysis_file = report_paths(csv_file, "perf-review")
    if output_file:
        summarized_csv = output_file

    print("🤖 Generating per-PR summaries...")
    summaries = []
    for idx, row in df.iterrows():
        print(f"Processing PR {idx + 1}/{len(df)}: {row['title'][:50]}...")
        summaries.append(summarizer.summarize_pr(row["title"], row["description"]))
        time.sleep(0.1)

    df = df.copy()
    df["ai_summary"] = summaries

    print("🔍 Analyzing patterns...")
    pattern_analysis = summarizer.analyze_pr_patterns(df.to_dict("records"))

    os.makedirs("output", exist_ok=True)
    df.to_csv(summarized_csv, index=False)
    print(f"💾 Saved summarized data to {summarized_csv}")

    with open(analysis_file, "w") as f:
        write_report_header(
            f,
            df,
            csv_file,
            title="GitHub PR Analysis Report",
            subtitle="*Mode: performance review*",
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

    print(f"📝 Saved report to {analysis_file}")
    print("\n🎯 QUICK ANALYSIS")
    print("=" * 50)
    print(pattern_analysis)

    return summarized_csv


def process_by_project(
    summarizer: PRSummarizer, df: pd.DataFrame, csv_file: str
) -> str:
    _, report_file = report_paths(csv_file, "by-project")
    pr_data = df.to_dict("records")

    print("📂 Summarizing by project area...")
    body = summarizer.generate_by_project_report(pr_data)

    os.makedirs("output", exist_ok=True)
    with open(report_file, "w") as f:
        write_report_header(
            f,
            df,
            csv_file,
            title="PRs by Project Area",
            subtitle="*Mode: by-project — progress summary per area*",
        )
        f.write(body)

    print(f"📝 Saved report to {report_file}")
    return report_file


def process_technical(
    summarizer: PRSummarizer, df: pd.DataFrame, csv_file: str
) -> str:
    _, report_file = report_paths(csv_file, "technical")
    pr_data = df.to_dict("records")

    print("🔬 Extracting technical highlights...")
    body = summarizer.generate_technical_report(pr_data)

    os.makedirs("output", exist_ok=True)
    with open(report_file, "w") as f:
        write_report_header(
            f,
            df,
            csv_file,
            title="Technical Highlights",
            subtitle="*Mode: technical — interesting implementation details only*",
        )
        f.write(body)

    print(f"📝 Saved report to {report_file}")
    return report_file


def process_pr_csv(
    csv_file: str,
    mode: str | None = None,
    output_file: str | None = None,
) -> str | None:
    mode = resolve_mode(mode)

    try:
        df = pd.read_csv(csv_file)
        print(f"📊 Loaded {len(df)} PRs from {csv_file}")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return None

    print(f"📋 Summarize mode: {mode}")
    summarizer = PRSummarizer()

    if mode == "perf-review":
        return process_perf_review(summarizer, df, csv_file, output_file)
    if mode == "by-project":
        return process_by_project(summarizer, df, csv_file)
    return process_technical(summarizer, df, csv_file)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize GitHub PRs using OpenAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""modes:
  perf-review   Full performance-review report (default)
  by-project    Group PRs by project with progress bullets
  technical     Technical highlights only; skip low-signal PRs

Examples:
  python src/pr_summarizer.py --mode by-project
  python src/pr_summarizer.py output/pr_2026-05-09_2026-05-16_detailed.csv --mode technical
  SUMMARIZE_MODE=by-project python src/pr_summarizer.py
""",
    )
    parser.add_argument("csv_file", nargs="?", help="CSV file to process")
    parser.add_argument("--output", help="Output CSV path (perf-review mode only)")
    parser.add_argument(
        "--mode",
        "-m",
        choices=SUMMARIZE_MODES,
        default=None,
        help=f"Report mode (default: {DEFAULT_MODE}, or SUMMARIZE_MODE env)",
    )
    return parser


def auto_detect_csv() -> str:
    output_dir = "output"
    if not os.path.exists(output_dir):
        print("❌ No output directory found.")
        print("Run the PR fetcher first to generate CSV data.")
        sys.exit(1)

    csv_files = [
        f"{output_dir}/{f}"
        for f in os.listdir(output_dir)
        if f.startswith("pr_")
        and f.endswith(".csv")
        and "summarized" not in f
    ]
    if not csv_files:
        print("❌ No PR CSV files found in output directory.")
        print("Run the PR fetcher first to generate CSV data.")
        sys.exit(1)

    csv_files.sort(key=os.path.getmtime, reverse=True)
    return csv_files[0]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    csv_file = args.csv_file or auto_detect_csv()
    if not args.csv_file:
        print(f"🔍 Auto-detected CSV file: {csv_file}")

    result = process_pr_csv(csv_file, mode=args.mode, output_file=args.output)
    if result:
        print(f"\n✅ Summary complete! Output: {result}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
