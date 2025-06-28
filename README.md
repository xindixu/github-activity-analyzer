# GitHub PR Analytics Suite

🤖 AI-powered GitHub PR analytics tool that transforms your pull request history into professional markdown reports with intelligent project categorization, pattern analysis, and performance insights.

## ✨ Features

- **📊 Complete Workflow**: Fetches PRs and generates AI analysis in one command
- **🤖 AI-Powered Insights**: Uses OpenAI to generate concise summaries and comprehensive pattern analysis
- **📁 Project Categorization**: Intelligently extracts project names from PR titles (`[CS-1234] ProjectName: description`)
- **📝 Professional Reports**: Generates beautiful markdown reports perfect for performance reviews
- **🔍 Comprehensive Analysis**: 5-section analysis covering project focus, technical themes, development velocity, cross-project insights, and key accomplishments
- **📈 Smart Metrics**: Tracks lines changed, PR distribution, and project priorities
- **🎯 Performance Review Ready**: Actionable insights for self-assessments and project planning

## 🏗️ Project Structure

```
pr/
├── src/
│   ├── github_pr_fetcher.py                     # Fetches PRs from GitHub
│   └── pr_summarizer.py                         # AI-powered analysis & summarization
├── output/
│   ├── pr_YYYY-MM-DD_YYYY-MM-DD_detailed.csv    # Raw PR data
│   ├── pr_YYYY-MM-DD_YYYY-MM-DD_summarized.csv  # With AI summaries
│   └── pr_YYYY-MM-DD_YYYY-MM-DD_summary.md      # Markdown analysis report
├── main.py                                      # Complete workflow entry point
├── requirements.txt                             # Dependencies
├── .env.example                                 # Configuration template
└── README.md
```

## 🚀 Quick Start

### 1. Installation

```bash
git clone <your-repo>
cd pr
pip install -r requirements.txt
```

### 2. Setup

Create a `.env` file with your configuration:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:
```env
# GitHub Configuration
GITHUB_TOKEN=your_personal_access_token_here
GITHUB_REPO=owner/repository
GITHUB_USERNAME=your_username  # Optional: specific user to search for

# Time Range (optional)
DAYS=14  # Default: 180 days (6 months)

# AI Configuration (for summarization)
OPENAI_API_KEY=your_openai_api_key_here
```

#### Getting GitHub Token
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo` (for private repos) or `public_repo` (for public repos)
4. Copy the generated token

#### Getting OpenAI API Key
1. Go to https://platform.openai.com/api-keys
2. Create a new API key
3. Copy the key (keep it secure!)

### 3. Run Complete Analysis

```bash
# Analyze last 14 days (default)
python main.py

# Custom time range
DAYS=30 python main.py

# Last 7 days
DAYS=7 python main.py
```

This will:
1. 📊 Fetch all your PRs from the specified time range
2. 🤖 Generate AI summaries for each PR
3. 🔍 Analyze patterns and categorize by project
4. 📝 Create a professional markdown report

## 📊 Output Files

### 1. **Detailed CSV** (`pr_YYYY-MM-DD_YYYY-MM-DD_detailed.csv`)
Raw PR data with clean descriptions:
- `pr_url` - Direct link to the PR
- `title` - PR title
- `description` - Clean description (removes boilerplate/templates)
- `lines_of_code_changes` - Total lines changed
- `additions` - Lines added
- `deletions` - Lines deleted
- `created_at` - PR creation timestamp
- `state` - PR state (open/closed)
- `merged` - Whether PR was merged
- `attachments` - URLs of attachments found in PR

### 2. **Summarized CSV** (`pr_YYYY-MM-DD_YYYY-MM-DD_summarized.csv`)
All detailed data plus:
- `ai_summary` - Concise AI-generated summary of each PR

### 3. **Analysis Report** (`pr_YYYY-MM-DD_YYYY-MM-DD_summary.md`)
Professional markdown report with:
- **📊 Executive Summary**: Period, totals, averages
- **🎯 Project Focus & Impact**: Which projects got the most attention
- **⚡ Technical Themes & Patterns**: Performance, security, infrastructure initiatives
- **🚀 Development Velocity & Scale**: Work distribution and iteration patterns
- **🔗 Cross-Project Insights**: Shared challenges and dependencies
- **🏆 Key Accomplishments & Trends**: Significant achievements and innovation
- **📋 Individual PR Details**: Each PR with project categorization, status, and summary

## 🎯 Project Categorization

The tool intelligently extracts project names from PR titles using the format:
```
[TICKET-123] ProjectName: Summary of changes
```

Examples:
- `[CS-6304] Roles: DB schema for RBAC` → **Roles** project
- `[CS-5916] Connector Catalog: update cypress tests` → **Connector Catalog** project
- `[INFRA-123] Docker: Update base images` → **Docker** project

PRs that don't match this pattern are categorized as "Uncategorized" and handled separately.

## ⚙️ Advanced Usage

### Run Components Separately

```bash
# Just fetch PR data
python src/github_pr_fetcher.py

# Just run AI analysis on existing CSV
python src/pr_summarizer.py
python src/pr_summarizer.py output/specific_file.csv
```

### Time Range Options

```bash
# Last week
DAYS=7 python main.py

# Last month
DAYS=30 python main.py

# Last quarter
DAYS=90 python main.py

# Last year
DAYS=365 python main.py
```

## 🎨 Sample Output

### Example Files
Check out the `examples/` directory for complete sample output demonstrating:

- **[Detailed CSV](examples/pr_2025-06-01_2025-06-30_detailed.csv)**: Raw PR data with 15 realistic pull requests
- **[Summarized CSV](examples/pr_2025-06-01_2025-06-30_summarized.csv)**: Same data enhanced with AI summaries
- **[Analysis Report](examples/pr_2025-06-01_2025-06-30_summary.md)**: Comprehensive markdown analysis
