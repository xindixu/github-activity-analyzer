#!/usr/bin/env python3
"""
GitHub PR Analyzer
Fetches PRs created by the authenticated user in the past 6 months,
filters out unimportant ones, and exports the data to CSV.
"""

import os
import csv
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, TypeVar

from github import Github
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()

T = TypeVar("T")

# Seconds between per-PR API calls (reduces ephemeral port exhaustion)
FETCH_DELAY_SEC = float(os.getenv("GITHUB_FETCH_DELAY", "0.3"))


def retry_github(
    fn: Callable[[], T],
    *,
    label: str = "GitHub API",
    max_attempts: int = 6,
    base_delay: float = 2.0,
) -> T:
    """Retry on transient network / port exhaustion errors (e.g. macOS errno 49)."""
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_error = e
            err = str(e).lower()
            transient = any(
                token in err
                for token in (
                    "errno 49",
                    "can't assign requested address",
                    "connection",
                    "timed out",
                    "max retries exceeded",
                    "temporarily unavailable",
                )
            )
            if not transient or attempt == max_attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            print(
                f"⚠️  {label} failed ({e!s:.120}); "
                f"retrying in {delay:.0f}s ({attempt + 1}/{max_attempts})..."
            )
            time.sleep(delay)
    raise last_error  # pragma: no cover


def parse_date(value: str, label: str) -> date:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{label} must be YYYY-MM-DD, got '{value}'") from exc


def resolve_fetch_range(
    *,
    days: Optional[int] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> tuple[date, date, str]:
    """
    Resolve the fetch window and GitHub search `created:` qualifier.

    Returns (start_date, end_date, created_search_fragment).
    """
    start = start or os.getenv("START_DATE")
    end = end or os.getenv("END_DATE")

    if start or end:
        if not start or not end:
            raise ValueError(
                "Both start and end dates are required (use --start/--end or "
                "START_DATE/END_DATE)"
            )
        start_d = parse_date(start, "start date")
        end_d = parse_date(end, "end date")
        if start_d > end_d:
            raise ValueError("start date must be on or before end date")
        created = f"created:{start_d.isoformat()}..{end_d.isoformat()}"
        return start_d, end_d, created

    days = days if days is not None else int(os.getenv("DAYS", "14"))
    if days <= 0:
        raise ValueError("DAYS must be a positive integer")

    end_d = datetime.now(timezone.utc).date()
    start_d = end_d - timedelta(days=days)
    created = f"created:>{start_d.isoformat()}"
    return start_d, end_d, created


def date_bounds(start_d: date, end_d: date) -> tuple[datetime, datetime]:
    """UTC bounds for filtering PR created_at (end date is inclusive)."""
    start_dt = datetime.combine(start_d, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_d, datetime.max.time(), tzinfo=timezone.utc)
    return start_dt, end_dt


_CURSOR_SUMMARY_BLOCK = re.compile(
    r"<!--\s*CURSOR_SUMMARY\s*-->(.*?)<!--\s*/CURSOR_SUMMARY\s*-->",
    re.DOTALL | re.IGNORECASE,
)
_CURSOR_SUMMARY_OPEN = re.compile(
    r"<!--\s*CURSOR_SUMMARY\s*-->.*",
    re.DOTALL | re.IGNORECASE,
)
_PLACEHOLDER_DESCRIPTIONS = frozenset({"todo", "tbd", "n/a"})


def _strip_blockquote_prefix(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith(">"):
        return stripped[1:].lstrip()
    return stripped


def _extract_overview_from_cursor_summary(cursor_text: str) -> str:
    """Keep only the Overview paragraph(s) from a CURSOR_SUMMARY block."""
    overview_lines: List[str] = []
    in_overview = False

    for line in cursor_text.splitlines():
        content = _strip_blockquote_prefix(line)

        if not in_overview:
            if re.fullmatch(r"\*\*Overview\*\*", content, re.IGNORECASE):
                in_overview = True
            continue

        if (
            content.startswith("<sup")
            or ("Reviewed by" in content and "Bugbot" in content)
            or content.startswith("[!")
            or (content == "---" and overview_lines)
        ):
            break
        if re.fullmatch(r"\*\*[^*]+\*\*", content):
            break

        overview_lines.append(content)

    while overview_lines and not overview_lines[0].strip():
        overview_lines.pop(0)
    while overview_lines and not overview_lines[-1].strip():
        overview_lines.pop()

    return "\n".join(overview_lines).strip()


def _extract_cursor_summary_raw(pr_body: str) -> str:
    match = _CURSOR_SUMMARY_BLOCK.search(pr_body)
    if match:
        return match.group(1).strip()
    open_match = _CURSOR_SUMMARY_OPEN.search(pr_body)
    if open_match:
        inner = open_match.group(0)
        inner = re.sub(
            r"<!--\s*CURSOR_SUMMARY\s*-->", "", inner, count=1, flags=re.IGNORECASE
        )
        return inner.strip()
    return ""


def _extract_cursor_summary(pr_body: str) -> str:
    raw = _extract_cursor_summary_raw(pr_body)
    if not raw:
        return ""
    return _extract_overview_from_cursor_summary(raw)


def _body_without_cursor_summary(pr_body: str) -> str:
    text = _CURSOR_SUMMARY_BLOCK.sub("", pr_body)
    text = _CURSOR_SUMMARY_OPEN.sub("", text)
    return text.strip()


def _is_meaningful_description(text: str) -> bool:
    normalized = text.strip()
    return bool(normalized) and normalized.lower() not in _PLACEHOLDER_DESCRIPTIONS


class PRAnalyzer:

    def __init__(self, github_token: str):
        """Initialize the PR analyzer with GitHub token."""
        self.github = Github(github_token)
        self.user = retry_github(lambda: self.github.get_user(), label="get_user")

    def get_pr_attachments(self, pr) -> List[str]:
        """Extract attachment URLs from PR body."""
        attachments = []
        if pr.body:
            # Look for markdown image syntax and links
            image_pattern = r'!\[.*?\]\((https?://[^\s\)]+)\)'
            link_pattern = r'\[.*?\]\((https?://[^\s\)]+)\)'

            attachments.extend(re.findall(image_pattern, pr.body))
            attachments.extend(re.findall(link_pattern, pr.body))

        return list(set(attachments))  # Remove duplicates

    def extract_important_description(self, pr_body: str) -> str:
        """
        Extract important content from PR description.
        Prefers the '## Description' section; otherwise the full body,
        or the CURSOR_SUMMARY Overview when that is the only substantive content.
        """
        if not pr_body:
            return ""

        lines = pr_body.split('\n')
        description_content = []
        in_description = False

        for line in lines:
            line_stripped = line.strip()

            if line_stripped == "## Description":
                in_description = True
                continue
            if line_stripped in ("## Test Plan", "## Checklist") or (
                line_stripped.startswith("##")
                and "checklist" in line_stripped.lower()
            ):
                break
            if line_stripped.startswith("<!---") or line_stripped.startswith("<!--"):
                break

            if in_description:
                description_content.append(line)

        desc_text = '\n'.join(description_content).strip()
        if desc_text and desc_text.lower() not in ['todo', 'tbd', 'n/a', '']:
            return desc_text

        if _is_meaningful_description(_body_without_cursor_summary(pr_body)):
            return pr_body.strip()

        cursor_summary = _extract_cursor_summary(pr_body)
        if _is_meaningful_description(cursor_summary):
            return cursor_summary

        return pr_body.strip()

    def fetch_user_prs(
        self,
        repo_name: str,
        github_username: str = None,
        *,
        days: Optional[int] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> List[Dict]:
        """Fetch PRs created by the user in the repo for a date range or past N days."""
        try:
            repo = self.github.get_repo(repo_name)
        except Exception as e:
            print(f"Error accessing repository {repo_name}: {e}")
            return []

        target_username = github_username or self.user.login
        start_d, end_d, created_clause = resolve_fetch_range(
            days=days, start=start, end=end
        )
        start_dt, end_dt = date_bounds(start_d, end_d)

        print(
            f"Fetching PRs from {repo_name} created by '{target_username}' "
            f"from {start_d.isoformat()} to {end_d.isoformat()}..."
        )

        search_query = (
            f"repo:{repo_name} is:pr author:{target_username} {created_clause}"
        )

        try:
            # Search for PRs matching our criteria
            issues = self.github.search_issues(query=search_query,
                                               sort='created',
                                               order='desc')
            total_count = issues.totalCount
            print(f"Found {total_count} PRs matching criteria")

            user_prs = []
            processed_count = 0

            for issue in issues:
                processed_count += 1
                if processed_count % 5 == 0:
                    print(f"Processed {processed_count}/{total_count} PRs...")

                    # Convert issue to PR object to get PR-specific data
                pr = retry_github(
                    lambda n=issue.number: repo.get_pull(n),
                    label=f"get_pull #{issue.number}",
                )
                time.sleep(FETCH_DELAY_SEC)

                if not (start_dt <= pr.created_at <= end_dt):
                    continue

                # Get attachments
                attachments = self.get_pr_attachments(pr)

                # Get line changes (this requires an additional API call)
                try:
                    lines_changed = pr.additions + pr.deletions
                    additions = pr.additions
                    deletions = pr.deletions
                except Exception as e:
                    print(
                        f"Warning: Could not get line count for PR #{pr.number}: {e}"
                    )
                    lines_changed = 0
                    additions = 0
                    deletions = 0

                pr_data = {
                    'pr_url':
                    pr.html_url,
                    'title':
                    pr.title,
                    'description':
                    self.extract_important_description(pr.body or ''),
                    'lines_of_code_changes':
                    lines_changed,
                    'additions':
                    additions,
                    'deletions':
                    deletions,
                    'created_at':
                    pr.created_at.isoformat(),
                    'state':
                    pr.state,
                    'merged':
                    pr.merged,
                    'attachments':
                    '; '.join(attachments) if attachments else ''
                }

                user_prs.append(pr_data)
                print(
                    f"Added PR: {pr.title} ({pr_data['lines_of_code_changes']} lines changed)"
                )

            return user_prs

        except Exception as e:
            print(f"Error searching for PRs: {e}")
            print("Falling back to the original method...")
            # Fallback to original method if search fails
            return self._fetch_user_prs_fallback(
                repo, target_username, start_dt, end_dt
            )

    def _fetch_user_prs_fallback(
        self, repo, target_username: str, start_dt: datetime, end_dt: datetime
    ) -> List[Dict]:
        """Fallback method using the original approach."""
        print("Using fallback method - this may be slower...")

        prs = repo.get_pulls(state="all", sort="created", direction="desc")

        user_prs = []
        processed_count = 0

        for pr in prs:
            processed_count += 1
            if processed_count % 50 == 0:
                print(f"Processed {processed_count} PRs...")

            if pr.created_at < start_dt:
                break
            if pr.created_at > end_dt:
                continue
            if pr.user.login != target_username:
                continue

            # Get attachments
            attachments = self.get_pr_attachments(pr)

            pr_data = {
                'pr_url': pr.html_url,
                'title': pr.title,
                'description': self.extract_important_description(pr.body
                                                                  or ''),
                'lines_of_code_changes': pr.additions + pr.deletions,
                'additions': pr.additions,
                'deletions': pr.deletions,
                'created_at': pr.created_at.isoformat(),
                'state': pr.state,
                'merged': pr.merged,
                'attachments': '; '.join(attachments) if attachments else ''
            }

            user_prs.append(pr_data)
            print(
                f"Added PR: {pr.title} ({pr_data['lines_of_code_changes']} lines changed)"
            )

        return user_prs

    def export_to_csv(self,
                      prs: List[Dict],
                      filename: str = 'output/pr_data_detailed.csv'):
        """Export PR data to detailed CSV file."""
        if not prs:
            print("No PRs to export.")
            return None

        # Ensure output directory exists
        import os
        os.makedirs('output', exist_ok=True)

        # Create DataFrame and export detailed CSV
        df = pd.DataFrame(prs)
        df.to_csv(filename, index=False, quoting=csv.QUOTE_ALL)
        print(f"Exported {len(prs)} PRs to {filename}")
        return filename


def main(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    days: Optional[int] = None,
) -> Optional[str]:
    """Main function to run the PR analyzer."""
    github_token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")
    github_username = os.getenv("GITHUB_USERNAME")

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required.")
        print(
            "Please set it in a .env file or export it as an environment variable."
        )
        return None

    if not repo_name:
        print("Error: GITHUB_REPO environment variable is required.")
        print(
            "Please set it in the format 'owner/repository' (e.g., 'facebook/react')."
        )
        return None

    try:
        start_d, end_d, _ = resolve_fetch_range(days=days, start=start, end=end)
    except ValueError as exc:
        print(f"Error: {exc}")
        return None

    if days is None and not (start or os.getenv("START_DATE")):
        days = int(os.getenv("DAYS", "14"))
        if days > 730:
            print(
                "Warning: Searching for more than 730 days (2 years) may take a very long time."
            )
            response = input("Continue? (y/N): ").lower().strip()
            if response != "y":
                return None

    try:
        analyzer = PRAnalyzer(github_token)

        target_user = github_username or analyzer.user.login
        print(f"Searching for PRs created by: {target_user}")
        print(f"Date range: {start_d.isoformat()} to {end_d.isoformat()}")

        prs = analyzer.fetch_user_prs(
            repo_name,
            github_username,
            days=days,
            start=start,
            end=end,
        )

        if not prs:
            print("No PRs found matching the criteria.")
            return None

        start_str = start_d.strftime("%Y-%m-%d")
        end_str = end_d.strftime("%Y-%m-%d")
        filename = f"output/pr_{start_str}_{end_str}_detailed.csv"
        csv_file = analyzer.export_to_csv(prs, filename)

        # Print summary
        print(f"\nSummary:")
        print(f"Total PRs found: {len(prs)}")
        print(
            f"Total lines changed: {sum(pr['lines_of_code_changes'] for pr in prs)}"
        )
        print(
            f"Average lines per PR: {sum(pr['lines_of_code_changes'] for pr in prs) / len(prs):.1f}"
        )

        return csv_file

    except Exception as e:
        print(f"Error: {e}")
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch GitHub PRs to CSV")
    parser.add_argument("--start", help="Start date (YYYY-MM-DD), inclusive")
    parser.add_argument("--end", help="End date (YYYY-MM-DD), inclusive")
    parser.add_argument(
        "--days",
        type=int,
        help="Past N days (ignored if --start/--end set; default: DAYS env or 14)",
    )
    cli = parser.parse_args()
    main(start=cli.start, end=cli.end, days=cli.days)
