#!/usr/bin/env python3
"""
GitHub PR Analyzer
Fetches PRs created by the authenticated user in the past 6 months,
filters out unimportant ones, and exports the data to CSV.
"""

import os
import csv
import re
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from github import Github
from dotenv import load_dotenv
import pandas as pd

# Load environment variables
load_dotenv()


class PRAnalyzer:

    def __init__(self, github_token: str):
        """Initialize the PR analyzer with GitHub token."""
        self.github = Github(github_token)
        self.user = self.github.get_user()

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
        Extract only the important content from PR description.
        Focuses on 'Description' and 'Test Plan' sections, removing boilerplate.
        """
        if not pr_body:
            return ""

        # Split the body into lines for easier processing
        lines = pr_body.split('\n')

        description_content = []
        test_plan_content = []
        current_section = None

        for line in lines:
            line_stripped = line.strip()

            # Detect section headers
            if line_stripped == "## Description":
                current_section = "description"
                continue
            elif line_stripped == "## Test Plan":
                current_section = "test_plan"
                continue
            elif line_stripped.startswith(
                    "## Checklist") or line_stripped.startswith(
                        "##") and "checklist" in line_stripped.lower():
                current_section = None  # Stop processing
                break
            elif line_stripped.startswith("<!---") or line_stripped.startswith(
                    "<!--"):
                current_section = None  # Stop at HTML comments
                break

            # Collect content for current section
            if current_section == "description":
                description_content.append(line)
            elif current_section == "test_plan":
                test_plan_content.append(line)

        # Clean and combine the content
        result_parts = []

        # Process description
        desc_text = '\n'.join(description_content).strip()
        if desc_text and desc_text.lower() not in ['todo', 'tbd', 'n/a', '']:
            result_parts.append(f"Description: {desc_text}")

        # Process test plan
        test_text = '\n'.join(test_plan_content).strip()
        if test_text and test_text.lower() not in ['todo', 'tbd', 'n/a', '']:
            result_parts.append(f"Test Plan: {test_text}")

        return '\n\n'.join(
            result_parts
        ) if result_parts else "No meaningful description available"

    def fetch_user_prs(self,
                       repo_name: str,
                       github_username: str = None,
                       days: int = 180) -> List[Dict]:
        """
        Fetch PRs created by the specified user in the specified repo
        within the past N days.
        """
        try:
            repo = self.github.get_repo(repo_name)
        except Exception as e:
            print(f"Error accessing repository {repo_name}: {e}")
            return []

        # Use provided username or fall back to authenticated user
        target_username = github_username or self.user.login

        # Calculate date threshold (timezone-aware to match GitHub API)
        threshold_date = datetime.now(timezone.utc) - timedelta(days=days)

        print(
            f"Fetching PRs from {repo_name} created by '{target_username}' after {threshold_date.strftime('%Y-%m-%d')}..."
        )

        # Use GitHub's search API to filter PRs by author - much more efficient!
        search_query = f"repo:{repo_name} is:pr author:{target_username} created:>{threshold_date.strftime('%Y-%m-%d')}"

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
                pr = repo.get_pull(issue.number)

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
            return self._fetch_user_prs_fallback(repo, target_username,
                                                 threshold_date)

    def _fetch_user_prs_fallback(self, repo, target_username: str,
                                 threshold_date) -> List[Dict]:
        """Fallback method using the original approach."""
        print("Using fallback method - this may be slower...")

        # Get all PRs (open and closed) created by the user
        prs = repo.get_pulls(state='all', sort='created', direction='desc')

        user_prs = []
        processed_count = 0

        for pr in prs:
            processed_count += 1
            if processed_count % 50 == 0:  # Less frequent updates for fallback
                print(f"Processed {processed_count} PRs...")

            # Check if PR is within date range
            if pr.created_at < threshold_date:
                break

                # Check if PR was created by the target user
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


def main():
    """Main function to run the PR analyzer."""
    # Get configuration from environment variables
    github_token = os.getenv('GITHUB_TOKEN')
    repo_name = os.getenv('GITHUB_REPO')
    github_username = os.getenv(
        'GITHUB_USERNAME')  # Optional: specific username to search for
    days_str = os.getenv('DAYS', '14')  # Default to 14 days if not specified

    if not github_token:
        print("Error: GITHUB_TOKEN environment variable is required.")
        print(
            "Please set it in a .env file or export it as an environment variable."
        )
        return

    if not repo_name:
        print("Error: GITHUB_REPO environment variable is required.")
        print(
            "Please set it in the format 'owner/repository' (e.g., 'facebook/react')."
        )
        return

    # Parse and validate days parameter
    try:
        days = int(days_str)
        if days <= 0:
            print("Error: DAYS must be a positive integer.")
            return
        if days > 730:  # More than 2 years
            print(
                "Warning: Searching for more than 730 days (2 years) may take a very long time."
            )
            response = input("Continue? (y/N): ").lower().strip()
            if response != 'y':
                return
    except ValueError:
        print(f"Error: DAYS must be a valid integer, got '{days_str}'.")
        return

    try:
        # Initialize analyzer
        analyzer = PRAnalyzer(github_token)

        # Show which user we're searching for and time range
        target_user = github_username or analyzer.user.login
        print(f"Searching for PRs created by: {target_user}")
        print(f"Time range: Past {days} day(s)")

        # Fetch PRs
        prs = analyzer.fetch_user_prs(repo_name, github_username, days)

        if not prs:
            print("No PRs found matching the criteria.")
            return None

        # Calculate date range for filename
        from datetime import datetime, timezone, timedelta
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Export to detailed CSV with date range in filename to output folder
        filename = f'output/pr_{start_str}_{end_str}_detailed.csv'
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
    main()
