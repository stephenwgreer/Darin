# GitHub Actions CI/CD Workflows

Comprehensive CI/CD pipelines for the Darin Audio Assistant project, integrated with enterprise bug-fix and feature workflows.

---

## Overview

Three workflows power the deployment pipeline:

| Workflow | Trigger | Purpose | Phase |
|----------|---------|---------|-------|
| **ci.yml** | PR/Push to `claude-redesign` or `main` | Code quality, testing, security | Phase 4 |
| **deploy-staging.yml** | Push to `claude-redesign` | Deploy to staging environment | Phase 7 |
| **deploy-production.yml** | Push to `main` | Deploy to production (requires approval) | Phase 9 |

---

## Workflow Integration

### Bug Fix Workflow (10 Steps)
- **Phase 4:** Implementation → CI runs automatically
- **Phase 5:** Code Review → Merge triggers staging deployment
- **Phase 7:** Staging Deployment → Automated via `deploy-staging.yml`
- **Phase 9:** Production Deployment → Manual approval required

### Feature Workflow (11 Steps)
- Same integration points as bug fix workflow
- Additional Phase 11: Documentation (after production)

---

## CI Pipeline (`ci.yml`)

### What It Does

**Package Manager Enforcement:**
- Python: ONLY `uv` allowed (fails on pip, conda, poetry)
- Node.js: ONLY `bun` allowed (fails on npm, yarn, pnpm)

**Python Checks:**
1. Install dependencies with `uv`
2. Run `ruff` linter
3. Run `mypy` type checker
4. Run `pytest` with coverage (target: 80%)
5. Security scan with `safety`

**TypeScript Checks** (if TS files exist):
1. Install dependencies with `bun`
2. Run `eslint`
3. Run `tsc` type check
4. Run `vitest` with coverage (target: 75%)
5. Security audit with `bun audit`

### When It Runs

```yaml
on:
  push:
    branches: [main, claude-redesign]
  pull_request:
    branches: [main, claude-redesign]
```

### Passing Criteria

- All linting errors fixed
- All type checks pass
- All tests pass
- Coverage meets thresholds
- No critical security vulnerabilities
- No unauthorized package managers used

---

## Staging Deployment (`deploy-staging.yml`)

### What It Does

1. **Pre-deployment validation**
   - Verify CI passed
   - Check environment configuration
   - Validate deployment phase

2. **Build application**
   - Install dependencies with `uv`
   - Create deployment artifact
   - Upload to GitHub artifacts

3. **Deploy to staging**
   - Deploy to staging platform (placeholder - configure yours)
   - Wait for stabilization

4. **Smoke tests**
   - Health check endpoint
   - Basic functionality tests
   - Performance baseline checks

5. **Post-deployment**
   - Create deployment report
   - Notify team
   - Ready for PM review (Phase 8)

### When It Runs

```yaml
on:
  push:
    branches: [claude-redesign]
  workflow_dispatch:  # Manual trigger
```

### Manual Trigger

```bash
# Via GitHub UI
GitHub → Actions → Deploy to Staging → Run workflow

# Via GitHub CLI
gh workflow run deploy-staging.yml
```

---

## Production Deployment (`deploy-production.yml`)

### What It Does

1. **Pre-production checks**
   - Verify all phases completed
   - Check deployment time (warns on Friday PM)
   - Validate rollback readiness

2. **Build production artifact**
   - Create optimized production package
   - Generate SHA256 checksum
   - Upload to artifacts (retained 30 days)

3. **MANUAL APPROVAL GATE** ⚠️
   - Requires explicit approval from PM/EM/Abbe
   - Uses GitHub Environments protection

4. **Deploy to production**
   - Verify artifact integrity
   - Deploy to production platform
   - Create Git release tag

5. **Health checks**
   - Production health endpoint
   - Critical functionality tests
   - Performance verification

6. **Post-production monitoring**
   - Initialize monitoring dashboards
   - Active monitoring for 30 minutes
   - Create deployment report

### When It Runs

```yaml
on:
  push:
    branches: [main]
  workflow_dispatch:  # Manual trigger with approval
```

### CRITICAL: Never Deploys Without Approval

Production deployments require manual approval from authorized users. This is enforced via GitHub Environments.

---

## Setup Instructions

### 1. Repository Settings

**Branch Protection Rules:**

Navigate to: `Settings → Branches → Add rule`

**For `claude-redesign` branch:**
```yaml
Branch name pattern: claude-redesign
Settings:
  ✓ Require a pull request before merging
  ✓ Require approvals (minimum: 1)
  ✓ Require status checks to pass before merging
    Required checks:
      - CI Pipeline Complete
      - Python CI (uv enforced)
  ✓ Require branches to be up to date before merging
  ✓ Require linear history
```

**For `main` branch:**
```yaml
Branch name pattern: main
Settings:
  ✓ Require a pull request before merging
  ✓ Require approvals (minimum: 2)
  ✓ Dismiss stale pull request approvals when new commits are pushed
  ✓ Require status checks to pass before merging
    Required checks:
      - CI Pipeline Complete
      - Python CI (uv enforced)
  ✓ Require branches to be up to date before merging
  ✓ Require linear history
  ✓ Do not allow bypassing the above settings
```

---

### 2. GitHub Environments

**Create Staging Environment:**

Navigate to: `Settings → Environments → New environment`

```yaml
Name: staging
Protection rules:
  Deployment branches: Selected branches
  Allowed branches: claude-redesign
Environment secrets:
  STAGING_DEPLOY_KEY: [your-staging-deploy-key]
  STAGING_API_URL: https://staging.darin-app.example.com
```

**Create Production Environment:**

```yaml
Name: production
Protection rules:
  ✓ Required reviewers
    Reviewers:
      - [PM username]
      - [EM username]
      - [Abbe username]
  Wait timer: 0 minutes (immediate approval required)
  Deployment branches: Selected branches
  Allowed branches: main
Environment secrets:
  PRODUCTION_DEPLOY_KEY: [your-production-deploy-key]
  PRODUCTION_API_URL: https://darin-app.example.com
  SENTRY_DSN: [optional-sentry-dsn]
  SLACK_WEBHOOK: [optional-slack-webhook]
```

---

### 3. Configure Deployment Platform

Choose one of the following platforms and configure the deployment steps in the workflows.

#### Option 1: Railway (Recommended for Python)

**Setup:**
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

# Get webhook URLs
railway webhooks create
```

**Update workflows:**
```yaml
# In deploy-staging.yml
- name: Deploy to staging platform
  run: railway up --environment staging

# In deploy-production.yml
- name: Deploy to production platform
  run: railway up --environment production
```

**Add secrets:**
```bash
# Get Railway token
railway whoami

# Add to GitHub Secrets:
# RAILWAY_TOKEN
```

---

#### Option 2: Render

**Setup:**
1. Create `render.yaml` in repository root:

```yaml
services:
  - type: web
    name: darin-app
    env: python
    buildCommand: "pip install uv && uv pip install -r requirements.txt"
    startCommand: "python main.py"
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
```

2. Connect repository to Render
3. Create staging and production services
4. Get deploy hook URLs

**Update workflows:**
```yaml
# In deploy-staging.yml
- name: Deploy to staging platform
  run: curl -X POST ${{ secrets.RENDER_STAGING_HOOK }}

# In deploy-production.yml
- name: Deploy to production platform
  run: curl -X POST ${{ secrets.RENDER_PRODUCTION_HOOK }}
```

**Add secrets:**
- `RENDER_STAGING_HOOK`
- `RENDER_PRODUCTION_HOOK`

---

#### Option 3: Heroku

**Setup:**
```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Login
heroku login

# Create staging app
heroku create darin-app-staging

# Create production app
heroku create darin-app

# Add PostgreSQL (if needed)
heroku addons:create heroku-postgresql:mini -a darin-app-staging
heroku addons:create heroku-postgresql:mini -a darin-app

# Get API key
heroku auth:token
```

**Update workflows:**
```yaml
# In deploy-staging.yml
- name: Deploy to staging platform
  run: |
    git remote add heroku-staging https://git.heroku.com/darin-app-staging.git
    git push heroku-staging claude-redesign:main

# In deploy-production.yml
- name: Deploy to production platform
  run: |
    git remote add heroku-prod https://git.heroku.com/darin-app.git
    git push heroku-prod main:main
```

**Add secrets:**
- `HEROKU_API_KEY`
- `HEROKU_EMAIL`

---

#### Option 4: Docker + AWS ECS

**Setup:**

1. Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

2. Configure AWS ECS cluster
3. Create ECR repository

**Update workflows:**
```yaml
# In deploy-staging.yml
- name: Deploy to staging platform
  run: |
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $ECR_REGISTRY
    docker build -t darin-app:staging .
    docker push $ECR_REGISTRY/darin-app:staging
    aws ecs update-service --cluster staging --service darin-app --force-new-deployment
```

**Add secrets:**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `ECR_REGISTRY`

---

### 4. Repository Secrets

Navigate to: `Settings → Secrets and variables → Actions → New repository secret`

**Required Secrets:**

```yaml
# Deployment
STAGING_DEPLOY_KEY: [platform-specific key]
PRODUCTION_DEPLOY_KEY: [platform-specific key]

# Monitoring (Optional)
SENTRY_DSN: [sentry.io DSN for error tracking]
SLACK_WEBHOOK: [Slack webhook for notifications]

# Platform-specific
RAILWAY_TOKEN: [if using Railway]
RENDER_STAGING_HOOK: [if using Render]
RENDER_PRODUCTION_HOOK: [if using Render]
HEROKU_API_KEY: [if using Heroku]
AWS_ACCESS_KEY_ID: [if using AWS]
AWS_SECRET_ACCESS_KEY: [if using AWS]
```

---

### 5. Add Health Check Endpoint

Before deploying, add a health check endpoint to your application:

**In `main.py` or create `health.py`:**
```python
from fastapi import FastAPI
from datetime import datetime
import os

app = FastAPI()

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "version": os.getenv("VERSION", "unknown"),
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

---

### 6. Environment Variables Configuration

**Create `.env.template`:**
```bash
# Required environment variables
ENVIRONMENT=development
DEEPGRAM_API_KEY=your-key-here
ANTHROPIC_API_KEY=your-key-here

# Optional
SENTRY_DSN=
LOG_LEVEL=INFO
```

**Add to `.gitignore`:**
```
.env
.env.local
.env.*.local
```

**Configure in platform:**
- Railway: `railway variables set ENVIRONMENT=staging`
- Render: Via dashboard → Environment variables
- Heroku: `heroku config:set ENVIRONMENT=staging -a darin-app-staging`

---

## Usage

### Standard Development Flow

```bash
# 1. Create feature branch from claude-redesign
git checkout claude-redesign
git pull origin claude-redesign
git checkout -b feature/my-feature

# 2. Develop feature
# ... make changes ...

# 3. Push branch (CI runs automatically)
git push origin feature/my-feature

# 4. Create PR to claude-redesign
gh pr create --base claude-redesign --title "Feature: My Feature"

# 5. CI runs on PR - must pass before merge
# Wait for: ✓ CI Pipeline Complete

# 6. Get code review approval
# Wait for: ✓ 1 approval

# 7. Merge PR (triggers staging deployment)
gh pr merge --squash

# 8. Staging deploys automatically
# GitHub Actions → Deploy to Staging → Monitor

# 9. Test in staging environment
# Visit: https://staging.darin-app.example.com

# 10. Create PR to main for production
git checkout main
git pull origin main
gh pr create --base main --head claude-redesign --title "Deploy: [Feature Name]"

# 11. Get PM approval + merge
# Wait for: ✓ 2 approvals (including PM)
gh pr merge --squash

# 12. Approve production deployment
# GitHub → Actions → Deploy to Production → Review deployments → Approve

# 13. Monitor production for 30 minutes
# Check: Error rates, response times, user reports
```

---

### Emergency Procedures

#### Rollback Staging Deployment

```bash
# Option 1: Revert via platform
railway rollback --environment staging

# Option 2: Git revert
git checkout claude-redesign
git revert HEAD
git push origin claude-redesign
# Staging redeploys automatically
```

#### Rollback Production Deployment (< 60 seconds)

```bash
# Option 1: Platform rollback
railway rollback --environment production

# Option 2: Git revert
git checkout main
git revert HEAD
git push origin main
# Manual approval still required, but can be expedited

# Option 3: Force rollback to previous tag
git checkout main
git reset --hard v20240209-143000  # Previous release tag
git push origin main --force
# CRITICAL: Only use in emergency, requires force push permission
```

#### CI Failure Resolution

```bash
# View failure logs
gh run view --log-failed

# Fix linting errors
source .venv/bin/activate
ruff check . --fix
git commit -am "fix: resolve linting errors"
git push

# Fix type errors
mypy . --exclude '.venv'
# Address errors
git commit -am "fix: resolve type errors"
git push

# Fix failing tests
pytest tests/ -v
# Fix tests
git commit -am "fix: resolve test failures"
git push
```

---

## Monitoring & Alerts

### Recommended Monitoring Stack

**Error Tracking: Sentry**
```bash
# Install
uv pip install sentry-sdk

# Configure in config.py
import sentry_sdk
sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment=os.getenv("ENVIRONMENT"),
    traces_sample_rate=1.0,
)
```

**Uptime Monitoring: UptimeRobot**
1. Create account at uptimerobot.com
2. Add monitor: https://darin-app.example.com/health
3. Check interval: 5 minutes
4. Alert via email/Slack

**Logs: Platform-specific**
```bash
# Railway
railway logs --tail

# Render
render logs --tail

# Heroku
heroku logs --tail -a darin-app

# AWS
aws logs tail /aws/ecs/darin-app --follow
```

### Alert Thresholds

**Critical (immediate action):**
- Error rate > 5%
- Response time p95 > 5 seconds
- Service down > 2 minutes
- Health check failing

**Warning (investigate):**
- Error rate > 1%
- Response time p95 > 2 seconds
- Memory usage > 85%
- CPU usage > 80%

---

## Troubleshooting

### CI Pipeline Fails with "uv not found"

**Problem:** uv installation failed

**Solution:**
```yaml
# Check uv installation step in ci.yml
- name: Install uv
  run: |
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo "$HOME/.cargo/bin" >> $GITHUB_PATH
```

### CI Fails with "pip install detected"

**Problem:** Code or CI config uses pip instead of uv

**Solution:**
```bash
# Find offending usage
grep -r "pip install" .

# Replace with uv
# ❌ pip install package
# ✅ uv pip install package
```

### Staging Deployment Fails

**Problem:** Deployment step fails

**Solution:**
1. Check deployment logs in GitHub Actions
2. Verify secrets are configured correctly
3. Check platform-specific logs
4. Verify environment variables are set

### Production Approval Not Showing

**Problem:** Can't approve production deployment

**Solution:**
1. Navigate to: `GitHub → Actions → Deploy to Production`
2. Click on running workflow
3. Look for "Review deployments" button
4. Select "production" environment
5. Add comment and click "Approve"

**If button missing:**
- Verify GitHub Environment "production" exists
- Verify you're listed as required reviewer
- Check branch protection rules

### Health Check Returns 404

**Problem:** Health check endpoint not implemented

**Solution:**
Add health check endpoint to your application (see Setup Instructions #5)

---

## Advanced Configuration

### Custom Coverage Thresholds

Edit `ci.yml`:
```yaml
- name: Check coverage threshold
  run: |
    coverage report --fail-under=80  # Change to desired percentage
```

### Add Deployment Notifications

Edit `deploy-production.yml`:
```yaml
- name: Notify team
  run: |
    curl -X POST ${{ secrets.SLACK_WEBHOOK }} \
      -H 'Content-Type: application/json' \
      -d '{
        "text": "🚀 Production deployed: ${{ github.sha }}",
        "channel": "#deployments",
        "username": "GitHub Actions"
      }'
```

### Enable Automatic Rollback

Add to `deploy-production.yml`:
```yaml
- name: Automatic rollback on health check failure
  if: failure()
  run: |
    railway rollback --environment production
    # Or platform-specific rollback command
```

### Add Database Migrations

Add before deployment step:
```yaml
- name: Run database migrations
  run: |
    source .venv/bin/activate
    # For Alembic
    alembic upgrade head
    # For Django
    python manage.py migrate
```

---

## Security Best Practices

1. **Never commit secrets** - Use GitHub Secrets only
2. **Rotate secrets regularly** - Every 90 days minimum
3. **Use environment-specific secrets** - Different keys for staging/production
4. **Enable Dependabot** - Automatic security updates
5. **Review deployment logs** - Don't expose sensitive data
6. **Use HTTPS only** - No HTTP in production
7. **Implement rate limiting** - Protect production APIs
8. **Enable 2FA** - For all GitHub users with production access

---

## Workflow Maintenance

### Regular Tasks

**Weekly:**
- Review failed workflow runs
- Check for outdated dependencies
- Review coverage trends

**Monthly:**
- Update workflow actions to latest versions
- Review and update secret rotation
- Performance audit of CI/CD pipeline

**Quarterly:**
- Review deployment procedures
- Update rollback documentation
- Conduct deployment dry-run

### Updating Workflows

```bash
# 1. Create branch
git checkout -b update/workflows
cd .github/workflows

# 2. Edit workflow files
vim ci.yml

# 3. Test changes
git add .
git commit -m "ci: update workflow configuration"
git push origin update/workflows

# 4. Create PR
gh pr create --title "Update CI/CD workflows"

# 5. Test in PR environment
# Verify all checks pass

# 6. Merge
gh pr merge --squash
```

---

## Support

**Questions about workflows:**
- Engineering Manager (EM)
- DevOps Sub-Agent

**Deployment issues:**
- DevOps Sub-Agent
- Head of Engineering (HoE)

**Production incidents:**
- On-call engineer
- Engineering Manager

**Documentation:**
- `.github/workflows/README.md` (this file)
- `engineering-manager/.claude/skills/deploy/`
- `engineering-manager/.claude/agents/devops.md`

---

## Workflow Status Badges

Add to your `README.md`:

```markdown
![CI Pipeline](https://github.com/[user]/[repo]/workflows/CI%20Pipeline/badge.svg)
![Deploy Staging](https://github.com/[user]/[repo]/workflows/Deploy%20to%20Staging/badge.svg)
![Deploy Production](https://github.com/[user]/[repo]/workflows/Deploy%20to%20Production/badge.svg)
```

---

**Version:** 1.0
**Last Updated:** 2026-02-09
**Maintained by:** DevOps Sub-Agent

For the latest updates, see: `.github/workflows/README.md`
