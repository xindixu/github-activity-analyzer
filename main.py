#!/usr/bin/env python3
"""
Main entry point for GitHub PR Analytics Suite
Complete workflow: fetches PRs from GitHub and then generates AI summaries.
"""

if __name__ == "__main__":
    try:
        import sys
        import os
        from pathlib import Path

        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

        from pr_summarizer import build_parser, process_pr_csv, report_paths, resolve_mode

        parser = build_parser()
        # main.py only needs --mode; csv is produced by the fetch step
        args, _ = parser.parse_known_args()

        mode = resolve_mode(args.mode)

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
        print(f"🤖 Step 2: Generating report (mode: {mode})...")
        summary_file = process_pr_csv(csv_file, mode=mode)

        if summary_file:
            print()
            print("🎉 WORKFLOW COMPLETE!")
            print("=" * 50)
            print(f"📁 Detailed PR data: {csv_file}")
            _, report_md = report_paths(csv_file, mode)
            print(f"📝 Report: {report_md}")
            if mode == "perf-review":
                print(f"🤖 Summarized CSV: {summary_file}")

            reports_dir = os.getenv("PR_REPORTS_DIR")
            if reports_dir:
                print()
                print("📤 Publishing reports to pr-reports...")
                from publish_reports import prefix_from_csv, publish

                prefix = prefix_from_csv(Path(csv_file))
                push = os.getenv("PUBLISH_PUSH", "").lower() in ("1", "true", "yes")
                try:
                    publish(prefix, push=push)
                except Exception as exc:
                    print(f"⚠️  Publish failed: {exc}")
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
