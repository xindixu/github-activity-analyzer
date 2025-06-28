#!/usr/bin/env python3
"""
Main entry point for GitHub PR Analytics Suite
Complete workflow: fetches PRs from GitHub and then generates AI summaries.
"""

if __name__ == "__main__":
    try:
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

        print("🚀 Starting GitHub PR Analytics Suite")
        print("=" * 50)

        # Step 1: Fetch PRs from GitHub
        print("📊 Step 1: Fetching PRs from GitHub...")
        from github_pr_fetcher import main as fetch_prs
        csv_file = fetch_prs()

        if not csv_file:
            print("❌ PR fetching failed. Stopping workflow.")
            sys.exit(1)

        print(f"✅ PR data saved to: {csv_file}")
        print()

        # Step 2: Generate AI summaries
        print("🤖 Step 2: Generating AI summaries...")
        from pr_summarizer import process_pr_csv
        summary_file = process_pr_csv(csv_file)

        if summary_file:
            print()
            print("🎉 WORKFLOW COMPLETE!")
            print("=" * 50)
            print(f"📁 Detailed PR data: {csv_file}")
            print(f"🤖 AI summarized data: {summary_file}")
            print(
                f"📝 Pattern analysis: {summary_file.replace('_summarized.csv', '_summary.md')}"
            )
        else:
            print("⚠️  PR fetching completed, but AI summarization failed.")
            print(f"📁 You can still use the detailed PR data: {csv_file}")

    except ImportError as e:
        print(f"❌ Error: Could not import required modules: {e}")
        print(
            "Make sure both github_pr_fetcher.py and pr_summarizer.py are in the src directory."
        )
        print("Also ensure you have all required dependencies installed:")
        print("  pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Error running PR Analytics Suite: {e}")
        sys.exit(1)
