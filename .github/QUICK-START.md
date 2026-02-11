# CI/CD Quick Start Guide

Get up and running with GitHub Actions CI/CD in 30 minutes.

---

## Prerequisites

- GitHub repository with admin access
- Python 3.11+ installed
- uv package manager installed
- GitHub CLI (gh) installed (optional but recommended)

---

## Step 1: Run Setup Script (5 minutes)

```bash
cd /mnt/c/Users/stwgre/github/Darin_AA/claude-redesign
./.github/setup-ci-cd.sh
```

Follow the interactive prompts. The script will:
- Check your environment
- Guide you through configuration
- Test CI checks locally
- Create .env.template

---

## Step 2: Configure GitHub Settings (10 minutes)

### A. Branch Protection

1. Go to: **Settings → Branches → Add rule**

2. For `claude-redesign` branch:
   - Pattern: `claude-redesign`
   - ☑ Require pull request before merging
   - ☑ Require approvals: 1
   - ☑ Require status checks to pass
   - Required checks: `CI Pipeline Complete`
   - Click **Create**

3. For `main` branch:
   - Pattern: `main`
   - ☑ Require pull request before merging
   - ☑ Require approvals: 2
   - ☑ Require status checks to pass
   - Required checks: `CI Pipeline Complete`
   - ☑ Do not allow bypassing the above settings
   - Click **Create**

### B. Create Environments

1. Go to: **Settings → Environments → New environment**

2. Create **staging** environment:
   - Name: `staging`
   - Deployment branches: Selected branches → `claude-redesign`
   - Click **Configure environment**

3. Create **production** environment:
   - Name: `production`
   - ☑ Required reviewers
   - Add reviewers: [Your PM, EM, or Abbe's GitHub usernames]
   - Deployment branches: Selected branches → `main`
   - Click **Configure environment**

---

## Step 3: Add Secrets (5 minutes)

1. Go to: **Settings → Secrets and variables → Actions**

2. Click **New repository secret**

3. Add these secrets (you'll add deployment keys after choosing platform):
   - Name: `STAGING_DEPLOY_KEY` → Value: (will add later)
   - Name: `PRODUCTION_DEPLOY_KEY` → Value: (will add later)

**Optional monitoring secrets:**
   - `SENTRY_DSN` → (for error tracking)
   - `SLACK_WEBHOOK` → (for notifications)

---

## Step 4: Commit Workflows (2 minutes)

```bash
# Commit the workflow files
git add .github/ .coveragerc ruff.toml .gitignore
git commit -m "ci: add GitHub Actions workflows and configuration"
git push origin claude-redesign
```

---

## Step 5: Test CI Pipeline (5 minutes)

```bash
# Create test branch
git checkout -b test/ci-verification

# Make a trivial change
echo "# CI Test" >> README.md
git add README.md
git commit -m "test: verify CI pipeline"
git push origin test/ci-verification

# Create PR
gh pr create --base claude-redesign --title "Test: Verify CI Pipeline" --body "Testing CI workflows"
```

**Expected result:**
- GitHub Actions tab shows "CI Pipeline" workflow running
- Workflow should pass (green checkmark)
- If fails, check logs and fix errors

**View workflow:**
```bash
gh run list
gh run view --log  # View latest run logs
```

---

## Step 6: Choose Deployment Platform (3 minutes)

**Recommended: Railway**

### Option A: Railway (Easiest for Python)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Create staging environment
railway environment create staging

# Create production environment
railway environment create production

# Get project token
railway whoami
```

**Add to GitHub Secrets:**
- `RAILWAY_TOKEN` → Your Railway token

**Update workflows:**
Edit `.github/workflows/deploy-staging.yml` line ~78:
```yaml
- name: Deploy to staging platform
  run: railway up --environment staging
```

Edit `.github/workflows/deploy-production.yml` line ~150:
```yaml
- name: Deploy to production platform
  run: railway up --environment production
```

### Option B: Other Platforms

See `.github/workflows/README.md` for:
- Render configuration
- Heroku configuration
- Docker + AWS configuration

---

## Step 7: Add Health Check Endpoint (REQUIRED)

Add to your `main.py`:

```python
from fastapi import FastAPI
from datetime import datetime
import os

app = FastAPI()

@app.get("/health")
def health_check():
    """Health check endpoint for deployment verification"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": os.getenv("VERSION", "dev"),
    }
```

**Or for Flask:**
```python
from flask import Flask, jsonify
from datetime import datetime
import os

app = Flask(__name__)

@app.route("/health")
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
    })
```

**Commit:**
```bash
git add main.py  # or your app file
git commit -m "feat: add health check endpoint"
git push origin claude-redesign
```

---

## Step 8: Test Staging Deployment (Optional)

```bash
# Merge test PR to claude-redesign
gh pr merge test/ci-verification --squash

# Watch staging deployment
gh run watch
# Or visit: GitHub → Actions → Deploy to Staging
```

**Expected result:**
- Deployment workflow starts automatically
- Builds application
- Deploys to staging platform
- Runs health checks

---

## That's It!

You're now ready to use the CI/CD pipeline.

---

## Daily Usage

### Develop a Feature

```bash
# 1. Create feature branch
git checkout claude-redesign
git pull
git checkout -b feature/my-feature

# 2. Make changes
# ... code ...

# 3. Push and create PR
git push origin feature/my-feature
gh pr create --base claude-redesign --title "Feature: My Feature"

# 4. CI runs automatically - wait for green checkmark

# 5. Get code review approval

# 6. Merge (staging deploys automatically)
gh pr merge --squash
```

### Deploy to Production

```bash
# 1. Create PR from claude-redesign to main
gh pr create --base main --head claude-redesign --title "Deploy: [Feature Name]"

# 2. Get PM approval + 2nd approval

# 3. Merge
gh pr merge --squash

# 4. Go to GitHub → Actions → Deploy to Production

# 5. Click "Review deployments" → Select "production" → Approve

# 6. Monitor deployment

# 7. Verify: curl https://your-app.com/health
```

---

## Troubleshooting

### CI Fails

**View logs:**
```bash
gh run view --log-failed
```

**Common fixes:**
```bash
# Linting errors
ruff check . --fix

# Type errors
mypy . --exclude '.venv'

# Test failures
pytest tests/ -v
```

### Deployment Fails

**Check logs:** GitHub → Actions → Click failed workflow

**Common issues:**
- Missing secrets (add in Settings → Secrets)
- Platform not configured (see Step 6)
- Health check endpoint missing (see Step 7)

### Can't Approve Production

**Check:**
1. You're listed as required reviewer (Settings → Environments → production)
2. Navigate to: Actions → Deploy to Production → Click "Review deployments"
3. Select "production" environment → Approve

---

## Need More Help?

**Comprehensive guides:**
- `.github/workflows/README.md` - Full documentation (20KB)
- `.github/CI-CD-SETUP-SUMMARY.md` - Quick reference (17KB)
- `.github/DEPLOYMENT-CHECKLIST.md` - Pre-deployment checklist (6KB)

**Platform-specific:**
- Railway: `.github/workflows/README.md` → Section 3 → Option 1
- Render: `.github/workflows/README.md` → Section 3 → Option 2
- Heroku: `.github/workflows/README.md` → Section 3 → Option 3

**Emergency rollback:**
```bash
# Fastest method
railway rollback --environment production

# Or git revert
git checkout main
git revert HEAD
git push origin main
# Then approve deployment
```

---

## Summary Checklist

- [ ] Run setup script
- [ ] Configure branch protection (claude-redesign + main)
- [ ] Create GitHub Environments (staging + production)
- [ ] Add repository secrets
- [ ] Commit workflow files
- [ ] Test CI pipeline
- [ ] Choose and configure deployment platform
- [ ] Add health check endpoint
- [ ] Test staging deployment (optional)
- [ ] Ready to deploy!

---

**Time to complete:** ~30 minutes
**Difficulty:** Intermediate
**Result:** Automated CI/CD pipeline with safe deployments

**Questions?** Check `.github/workflows/README.md` for detailed answers.

---

**Happy deploying! 🚀**
