# GitHub Actions Setup

This project includes GitHub Actions workflows to automatically run the stock screener and maintain code quality.

## Workflows

### 1. Run Stock Screener (`run-screener.yml`)
Automatically runs the stock screener and saves results to CSV.

**Trigger:**
- **Schedule**: Every Monday at 1:00 PM UTC (after US market close)
- **Manual**: Can be triggered manually from the GitHub Actions tab

**What it does:**
1. Checks out the latest code
2. Sets up Python 3.11
3. Installs dependencies
4. Runs the headless screener
5. Saves results to `results/screener_results_YYYYMMDD.csv`
6. Commits and pushes results back to the repository
7. Uploads results as a GitHub Actions artifact (90-day retention)

**Manual Trigger Options:**
- `index`: Which index to screen (S&P 500, NASDAQ, DOW) - optional
- `min_rs`: Minimum RS rating (default: 70) - optional

**To manually trigger:**
1. Go to **Actions** tab
2. Select **"Run Stock Screener"**
3. Click **"Run workflow"**
4. (Optional) Customize inputs

### 2. Code Quality Checks (`code-quality.yml`)
Validates code formatting and imports on every push and pull request.

**Trigger:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**What it checks:**
- **Black**: Code formatting consistency
- **isort**: Import sorting
- **Flake8**: PEP8 violations and potential errors
- **Pylint**: Code quality and potential bugs
- **pip check**: Dependency conflicts

## Setup Instructions

### Step 1: Push Changes to GitHub
```bash
git add .github/ results/.gitkeep screener_headless.py
git commit -m "feat: add GitHub Actions workflows"
git push
```

### Step 2: Enable Actions (if needed)
1. Go to your repository on GitHub
2. Click the **Actions** tab
3. If workflows are disabled, click "Enable workflows"

### Step 3: Configure Automatic Commits (Optional)
The screener workflow automatically commits results using a bot account. This works out-of-the-box with GitHub's `GITHUB_TOKEN`.

### Step 4: View Results
- **Results CSV**: `results/` directory in the repository
- **Logs**: GitHub Actions > Workflow runs > Click a run to see logs
- **Artifacts**: Download raw CSV files from artifact storage

## Customizing the Schedule

To change when the screener runs, edit `.github/workflows/run-screener.yml`:

```yaml
schedule:
  # Change this cron expression
  - cron: '0 13 * * 1'  # Monday 1:00 PM UTC
```

### Cron Format
```
minute hour day-of-month month day-of-week
  0     13        *        *      1
```

**Common examples:**
- `0 13 * * 1` - Every Monday at 1:00 PM UTC
- `0 13 * * 1-5` - Every weekday at 1:00 PM UTC
- `0 9,17 * * 1-5` - Every weekday at 9 AM and 5 PM UTC

[Cron syntax reference](https://crontab.guru/)

## Using the Headless Screener Locally

You can also run the screener from the command line:

```bash
# Screen S&P 500 (default)
python screener_headless.py --output results/sp500.csv

# Screen NASDAQ
python screener_headless.py --index nasdaq --output results/nasdaq.csv

# Screen with minimum RS rating of 80
python screener_headless.py --min-rs 80 --output results/high_rs.csv

# Show all options
python screener_headless.py --help
```

## Troubleshooting

### Workflow fails with "yfinance" errors
- This usually happens when Yahoo Finance has rate limits
- GitHub Actions will retry automatically
- Check logs in the Actions tab

### Results not being committed
- Ensure GitHub Actions are enabled
- Check that the repository has write permissions
- View detailed logs in the Actions tab

### Need to adjust the screener logic
- Edit `screener_headless.py` or `indicators.py`
- Create a pull request to test changes
- Code quality checks will validate your changes

## Next Steps

1. ✅ GitHub Actions workflows are configured
2. Push to GitHub to activate workflows
3. Monitor runs in the **Actions** tab
4. Download results from the **results/** folder
5. (Optional) Set up notifications for workflow failures

## Workflow Status Badge

Add this to your README.md to show workflow status:

```markdown
![Run Stock Screener](https://github.com/YOUR_USERNAME/mark_minervini_stock_screener/actions/workflows/run-screener.yml/badge.svg)
![Code Quality](https://github.com/YOUR_USERNAME/mark_minervini_stock_screener/actions/workflows/code-quality.yml/badge.svg)
```

Replace `YOUR_USERNAME` with your actual GitHub username.
