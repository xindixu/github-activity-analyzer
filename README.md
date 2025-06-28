# GitHub PR Analytics Suite

A two-part Python tool to fetch and analyze your GitHub pull requests. Includes a fetcher to collect PR data and an analyzer to process and gain insights from the data.

## Project Structure

```
pr/
├── src/                           # Source code
│   ├── github_pr_fetcher.py      # Fetches PRs from GitHub
│   └── pr_summarizer.py          # AI-powered analysis
├── output/                        # Generated files
│   ├── pr_YYYY-MM-DD_YYYY-MM-DD_detailed.csv
│   ├── pr_YYYY-MM-DD_YYYY-MM-DD_detailed_summarized.csv
│   └── pr_YYYY-MM-DD_YYYY-MM-DD_detailed_summary.txt
├── main.py                        # Main entry point
├── requirements.txt               # Dependencies
├── .env.example                   # Configuration template
└── README.md                      # This file
```

## Components

### 1. **GitHub PR Fetcher** (`src/github_pr_fetcher.py`)
- Fetches PRs created by you in a configurable time range (days)
- Extracts clean descriptions (removes boilerplate/templates)
- Calculates lines of code changes for each PR
- Extracts attachment URLs from PR descriptions
- Exports data with date-based naming to `output/` directory

### 2. **AI-Powered Summarizer** (`src/pr_summarizer.py`)
- Uses OpenAI to generate concise PR summaries
- Analyzes patterns across all your PRs
- Identifies key development themes and trends
- Auto-detects latest data files

## Installation

1. Clone or download this project
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Setup

1. Create a GitHub Personal Access Token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Select scopes: `repo` (for private repos) or `public_repo` (for public repos only)
   - Copy the generated token

2. Configure environment variables:
   ```bash
   cp .env.example .env
   ```

3. Edit the `.env` file and add your values:
   ```
   GITHUB_TOKEN=your_personal_access_token_here
   GITHUB_REPO=owner/repository
   ```

## Usage

### Fetch PR Data

Run the main script to collect your PR data:
```bash
python main.py
```

Or run the fetcher directly:
```bash
python src/github_pr_fetcher.py
```

The script will:
1. Connect to GitHub using your token
2. Fetch all PRs you created in the specified repository and time range
3. Extract clean descriptions (removing boilerplate)
4. Export the data to the `output/` directory with date-based naming:
   - `pr_YYYY-MM-DD_YYYY-MM-DD_detailed.csv` - Complete PR data with all columns

### Analyze with AI

Run the AI summarizer to get insights:
```bash
# Basic AI analysis (auto-detects latest file)
python src/pr_summarizer.py

# Specify a specific file
python src/pr_summarizer.py output/pr_2025-06-01_2025-06-28_detailed.csv

# Custom output name
python src/pr_summarizer.py --output my_analysis.csv
```

This generates:
- `pr_YYYY-MM-DD_YYYY-MM-DD_detailed_summarized.csv` - Original data + AI summaries
- `pr_YYYY-MM-DD_YYYY-MM-DD_detailed_summary.txt` - Pattern analysis report

## Output Columns

### Basic CSV (`github_prs.csv`):
- `pr_url` - Direct link to the PR
- `title` - PR title
- `description` - PR description/body
- `lines_of_code_changes` - Total lines added + deleted

### Detailed CSV (`github_prs_detailed.csv`):
- All basic columns plus:
- `additions` - Lines added
- `deletions` - Lines deleted
- `created_at` - PR creation timestamp
- `state` - PR state (open/closed)
- `merged` - Whether PR was merged
- `attachments` - URLs of any attachments found in the PR description

## Filtering Logic

The tool automatically filters out PRs that match these patterns:
- Typo fixes (contains "typo", "spelling", etc.)
- Small formatting changes (whitespace, linting, etc.)
- Dependency updates (version bumps, security updates)
- Documentation-only changes
- Configuration file updates
- PRs with less than 5 lines of changes

## Customization

You can modify the filtering logic by editing the `is_unimportant_pr()` method in `main.py`.

## Requirements

- Python 3.7+
- GitHub Personal Access Token
- Repository access (public or private based on token permissions)

## Troubleshooting

1. **Authentication Error**: Make sure your GitHub token is valid and has the correct permissions
2. **Repository Not Found**: Ensure the repository name is in the correct format (`owner/repository`)
3. **Rate Limiting**: GitHub API has rate limits. The script includes basic error handling, but you may need to wait if you hit limits.

## License

This project is open source and available under the MIT License.