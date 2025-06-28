# Example Output Files

This directory contains realistic example output from the GitHub PR Analytics Suite, demonstrating the tool's capabilities with 15 sample pull requests from a month-long development period.

## 📁 Files

### `pr_2025-06-01_2025-06-30_detailed.csv`
**Raw PR data** - Original output from the GitHub PR fetcher with:
- PR URLs, titles, and clean descriptions
- Lines changed metrics (total, additions, deletions)
- Creation dates, states, and merge status
- Attachment URLs from PR descriptions

### `pr_2025-06-01_2025-06-30_summarized.csv`
**Enhanced with AI summaries** - Same data as detailed CSV plus:
- `ai_summary` column with concise, AI-generated descriptions
- Professional summaries perfect for performance reviews

### `pr_2025-06-01_2025-06-30_summary.md`
**Comprehensive analysis report** - Professional markdown document with:
- Executive summary with key metrics
- 5-section AI analysis covering project focus, technical themes, development velocity, cross-project insights, and key accomplishments
- Individual PR details with project categorization and status indicators
