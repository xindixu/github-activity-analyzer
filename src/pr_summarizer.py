#!/usr/bin/env python3
"""
GitHub PR Summarizer
Uses OpenAI to generate concise summaries of PR descriptions and analyze patterns.
"""

import os
import sys
import pandas as pd
import json
import argparse
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class PRSummarizer:

    def __init__(self):
        """Initialize the summarizer with OpenAI."""
        self.client = None
        self.model = None
        self._setup_openai()

    def _setup_openai(self):
        """Setup OpenAI client."""
        try:
            import openai
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY environment variable required")
            self.client = openai.OpenAI(api_key=api_key)
            self.model = os.getenv('OPENAI_MODEL', 'gpt-3.5-turbo')
            print(f"✅ OpenAI client initialized with model: {self.model}")
        except ImportError:
            print("❌ OpenAI library not installed. Run: pip install openai")
            sys.exit(1)

    def _call_openai(self, prompt: str, max_tokens: int = 150) -> str:
        """Call OpenAI API."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{
                    "role":
                    "system",
                    "content":
                    "You are a helpful assistant that summarizes GitHub pull requests concisely and accurately."
                }, {
                    "role": "user",
                    "content": prompt
                }],
                max_tokens=max_tokens,
                temperature=0.3)
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"

    def summarize_pr(self, title: str, description: str) -> str:
        """Generate a concise summary of a single PR."""
        prompt = f"""Summarize this GitHub pull request in 1-2 concise sentences. Focus on what was changed and why.

Title: {title}

Description: {description}

Summary:"""

        return self._call_openai(prompt)

    def extract_project_from_title(self, title: str) -> str:
        """Extract project key from PR title format: [xxx-xxx] <project key>: xxx"""
        import re

        # Match pattern: [ticket] project: description
        # Examples: [CS-6304] Roles: something, [CS-0000] Roles: something
        pattern = r'\[([^\]]+)\]\s*([^:]+):'
        match = re.match(pattern, title)

        if match:
            ticket_id = match.group(1)
            project_key = match.group(2).strip()
            return project_key

        # Fallback: try to extract just the project name after ]
        fallback_pattern = r'\][^:]*?([A-Za-z][A-Za-z\s]+?):'
        fallback_match = re.search(fallback_pattern, title)
        if fallback_match:
            return fallback_match.group(1).strip()

        return "Uncategorized"

    def analyze_pr_patterns(self, pr_data: List[Dict]) -> str:
        """Analyze patterns across multiple PRs with project categorization."""
        # Extract project information and group PRs
        projects = {}
        for pr in pr_data:
            project = self.extract_project_from_title(pr['title'])
            if project not in projects:
                projects[project] = []
            projects[project].append(pr)

        # Build project breakdown
        project_breakdown = []
        for project, prs in projects.items():
            total_lines = sum(pr.get('lines_of_code_changes', 0) for pr in prs)
            project_breakdown.append(
                f"• {project}: {len(prs)} PRs, {total_lines} lines changed")

        # Combine summaries for AI analysis (limit to avoid token limits)
        combined_summaries = "\n".join([
            f"• [{self.extract_project_from_title(pr['title'])}] {pr.get('ai_summary', 'No summary')}"
            for pr in pr_data[:20]
        ])

        project_breakdown_text = "\n".join(project_breakdown)

        prompt = f"""Analyze these GitHub PR summaries and provide a comprehensive development activity report:

PROJECT BREAKDOWN:
{project_breakdown_text}

PR SUMMARIES BY PROJECT:
{combined_summaries}

Provide a detailed analysis covering:

1. **PROJECT FOCUS & IMPACT**
   - Which projects received the most attention and why
   - Relative impact based on lines changed and complexity
   - Project priorities and strategic focus areas

2. **TECHNICAL THEMES & PATTERNS**
   - Major technical initiatives (performance, security, infrastructure, features)
   - Architecture improvements and system optimizations
   - Testing and development workflow enhancements

3. **DEVELOPMENT VELOCITY & SCALE**
   - Distribution of effort across different types of work
   - Balance between feature development vs. bug fixes vs. maintenance
   - Code review and iteration patterns (based on PR descriptions)

4. **CROSS-PROJECT INSIGHTS**
   - Common technologies or approaches used across projects
   - Shared challenges or recurring themes
   - Dependencies or relationships between different projects

5. **KEY ACCOMPLISHMENTS & TRENDS**
   - Most significant changes or achievements
   - Quality improvements and technical debt reduction
   - Innovation or new capabilities introduced

Provide specific examples and quantify impact where possible. Focus on actionable insights for performance reviews and project planning.

Analysis:"""

        return self._call_openai(prompt, max_tokens=800)


def process_pr_csv(csv_file: str, output_file: str = None) -> str:
    """Process a CSV file of PRs and generate summaries."""
    # Load PR data
    try:
        df = pd.read_csv(csv_file)
        print(f"📊 Loaded {len(df)} PRs from {csv_file}")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return None

    # Initialize summarizer
    summarizer = PRSummarizer()

    # Generate summaries
    print("🤖 Generating AI summaries...")
    summaries = []

    for idx, row in df.iterrows():
        print(f"Processing PR {idx + 1}/{len(df)}: {row['title'][:50]}...")

        summary = summarizer.summarize_pr(row['title'], row['description'])
        summaries.append(summary)

        # Add a small delay to respect API rate limits
        import time
        time.sleep(0.1)

    # Add summaries to dataframe
    df['ai_summary'] = summaries

    # Generate pattern analysis
    print("🔍 Analyzing patterns...")
    # Convert DataFrame to list of dictionaries for analysis
    pr_data_list = df.to_dict('records')
    pattern_analysis = summarizer.analyze_pr_patterns(pr_data_list)

    # Ensure output directory exists
    import os
    os.makedirs('output', exist_ok=True)

    # Save results with new naming format
    if not output_file:
        # Extract date range from filename (pr_YYYY-MM-DD_YYYY-MM-DD.csv)
        base_name = os.path.basename(csv_file)
        if base_name.startswith('pr_') and base_name.endswith('.csv'):
            # Extract date range from filename, removing any suffix like '_detailed'
            date_part = base_name[3:-4]  # Remove 'pr_' and '.csv'
            # Remove '_detailed' suffix if present
            if date_part.endswith('_detailed'):
                date_part = date_part[:-9]  # Remove '_detailed'
            output_file = f"output/pr_{date_part}_summarized.csv"
        else:
            # Fallback to old naming
            base_name = os.path.splitext(csv_file)[0]
            output_file = f"{base_name}_summarized.csv"

    df.to_csv(output_file, index=False)
    print(f"💾 Saved summarized data to {output_file}")

    # Save pattern analysis with new naming format as markdown
    analysis_file = output_file.replace('_summarized.csv', '_summary.md')
    with open(analysis_file, 'w') as f:
        # Extract date range for title
        base_name = os.path.basename(output_file)
        if 'pr_' in base_name:
            date_part = base_name.replace('pr_',
                                          '').replace('_summarized.csv', '')
            date_range = date_part.replace('_', ' to ')
        else:
            date_range = "Development Period"

        f.write(f"# GitHub PR Analysis Report\n\n")
        f.write(f"**Period:** {date_range}  \n")
        f.write(f"**Total PRs:** {len(df)}  \n")
        f.write(
            f"**Total Lines Changed:** {df['lines_of_code_changes'].sum():,}  \n"
        )
        f.write(
            f"**Average Lines per PR:** {df['lines_of_code_changes'].mean():.1f}  \n\n"
        )

        f.write("---\n\n")
        f.write("## 📊 Development Activity Analysis\n\n")
        f.write(pattern_analysis)
        f.write("\n\n---\n\n")
        f.write("## 📋 Individual PR Summaries\n\n")

        for idx, (_, row) in enumerate(df.iterrows()):
            # Extract project from title for better organization
            project = "Uncategorized"
            import re
            pattern = r'\[([^\]]+)\]\s*([^:]+):'
            match = re.match(pattern, row['title'])
            if match:
                project = match.group(2).strip()

            f.write(f"### {idx + 1}. {row['title']}\n\n")
            f.write(f"**Project:** `{project}`  \n")
            f.write(
                f"**Lines Changed:** {row['lines_of_code_changes']} (+{row['additions']}, -{row['deletions']})  \n"
            )
            f.write(
                f"**Status:** {row['state'].title()} {'✅' if row['merged'] == True else '🔄' if row['state'] == 'open' else '❌'}  \n"
            )
            f.write(f"**URL:** {row['pr_url']}\n\n")
            f.write(f"**Summary:** {row['ai_summary']}\n\n")
            f.write("---\n\n")

    print(f"📝 Saved pattern analysis to {analysis_file}")

    # Print quick summary
    print("\n🎯 QUICK ANALYSIS")
    print("=" * 50)
    print(pattern_analysis)

    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Summarize GitHub PRs using OpenAI')
    parser.add_argument('csv_file', nargs='?', help='CSV file to process')
    parser.add_argument('--output', help='Output file name')

    args = parser.parse_args()

    # Auto-detect CSV file if not provided
    if not args.csv_file:
        import os
        output_dir = 'output'
        if not os.path.exists(output_dir):
            print("❌ No output directory found.")
            print("Run the PR fetcher first to generate CSV data.")
            sys.exit(1)

        csv_files = [
            f"{output_dir}/{f}" for f in os.listdir(output_dir)
            if f.startswith('pr_') and f.endswith('.csv')
            and 'summarized' not in f
        ]
        if not csv_files:
            print("❌ No PR CSV files found in output directory.")
            print("Run the PR fetcher first to generate CSV data.")
            sys.exit(1)

        # Use the most recent file
        csv_files.sort(key=os.path.getmtime, reverse=True)
        args.csv_file = csv_files[0]
        print(f"🔍 Auto-detected CSV file: {args.csv_file}")

    # Process the file
    result_file = process_pr_csv(args.csv_file, args.output)

    if result_file:
        print(f"\n✅ Summary complete! Check {result_file}")


if __name__ == "__main__":
    main()
