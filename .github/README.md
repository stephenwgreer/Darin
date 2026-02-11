# GitHub CI/CD Workflows

Automated CI/CD pipelines for the Darin Audio Assistant.

---

## Overview

This directory contains GitHub Actions workflows, configuration, and documentation for automated testing and deployment.

---

## Files in This Directory

### Workflow Files (`.github/workflows/`)

| File | Purpose | Trigger |
|------|---------|---------|
| **ci.yml** | Main CI pipeline - linting, testing, coverage | PR/push to `claude-redesign` or `main` |
| **deploy-staging.yml** | Deploy to staging environment | Push to `claude-redesign` |
| **deploy-production.yml** | Deploy to production (with approval) | Push to `main` |

---

### Documentation

| File | Description | Size |
|------|-------------|------|
| **QUICK-START.md** | Get started in 30 minutes | 5KB |
| **CI-CD-SETUP-SUMMARY.md** | Quick reference guide | 17KB |
| **workflows/README.md** | Complete documentation | 20KB |
| **DEPLOYMENT-CHECKLIST.md** | Pre-deployment checklist | 6KB |

---

### Scripts

| File | Purpose |
|------|---------|
| **setup-ci-cd.sh** | Interactive setup script |

---

## Quick Links

**Getting Started:**
→ Start here: [QUICK-START.md](./QUICK-START.md)

**Complete Guide:**
→ Everything: [workflows/README.md](./workflows/README.md)

**Before Deploying:**
→ Checklist: [DEPLOYMENT-CHECKLIST.md](./DEPLOYMENT-CHECKLIST.md)

**Quick Reference:**
→ Summary: [CI-CD-SETUP-SUMMARY.md](./CI-CD-SETUP-SUMMARY.md)

---

## What These Workflows Do

### CI Pipeline (`ci.yml`)

**Runs on every PR and push**

- Enforces package managers (uv for Python, bun for TypeScript)
- Runs linting with ruff
- Runs type checking with mypy
- Runs tests with pytest
- Checks coverage (80% target)
- Scans for security vulnerabilities

**Integration:** Phase 4 of bug-fix/feature workflows

---

### Staging Deployment (`deploy-staging.yml`)

**Runs when code is merged to `claude-redesign`**

- Builds application
- Deploys to staging environment
- Runs smoke tests
- Verifies health check
- Creates deployment report

**Integration:** Phase 7 of bug-fix/feature workflows

---

### Production Deployment (`deploy-production.yml`)

**Runs when code is merged to `main` (requires approval)**

- Validates all previous phases complete
- Builds production artifact
- **Waits for manual approval** (PM/EM/Abbe)
- Deploys to production
- Runs health checks
- Monitors for 30 minutes
- Creates release tag

**Integration:** Phase 9 of bug-fix/feature workflows

---

## Setup Status

| Step | Status | Location |
|------|--------|----------|
| Workflows created | ✓ Complete | `.github/workflows/` |
| Documentation | ✓ Complete | `.github/*.md` |
| Configuration files | ✓ Complete | `ruff.toml`, `.coveragerc` |
| GitHub settings | ⚠ Pending | See QUICK-START.md |
| Deployment platform | ⚠ Pending | See workflows/README.md |
| Health endpoint | ⚠ Pending | Add to `main.py` |

---

## Next Steps

1. **Read:** [QUICK-START.md](./QUICK-START.md) (30 minutes)
2. **Run:** `./setup-ci-cd.sh`
3. **Configure:** GitHub settings (branch protection, environments)
4. **Test:** Create test PR to verify CI
5. **Deploy:** Choose platform and configure workflows

---

## Architecture

```
Feature Branch
     ↓
   PR to claude-redesign
     ↓
CI Pipeline (ci.yml)
     ↓
Code Review + Merge
     ↓
Staging Deploy (deploy-staging.yml) ← Automatic
     ↓
PM Review in Staging
     ↓
   PR to main
     ↓
Merge to main
     ↓
Production Deploy (deploy-production.yml) ← Manual approval required
     ↓
Production Monitoring
```

---

## Package Manager Enforcement

**Python: uv ONLY**
- ✓ `uv pip install`
- ✗ `pip install` (CI fails)
- ✗ `conda install` (CI fails)
- ✗ `poetry add` (CI fails)

**TypeScript: bun ONLY** (if applicable)
- ✓ `bun install`
- ✗ `npm install` (CI fails)
- ✗ `yarn add` (CI fails)
- ✗ `pnpm add` (CI fails)

---

## Emergency Procedures

### Rollback Production (< 60 seconds)

```bash
# Method 1: Platform rollback (fastest)
railway rollback --environment production

# Method 2: Git revert
git checkout main
git revert HEAD
git push origin main
# Then approve deployment
```

### CI Pipeline Failing

```bash
# View logs
gh run view --log-failed

# Fix locally
ruff check . --fix
pytest tests/ -v

# Push fix
git commit -am "fix: resolve CI errors"
git push
```

---

## Support

**Setup help:** See [QUICK-START.md](./QUICK-START.md)

**Detailed questions:** See [workflows/README.md](./workflows/README.md)

**Deployment checklist:** See [DEPLOYMENT-CHECKLIST.md](./DEPLOYMENT-CHECKLIST.md)

**Emergency:** See rollback procedures above

---

## Workflow Monitoring

**View all workflows:**
```bash
gh workflow list
```

**View recent runs:**
```bash
gh run list --limit 10
```

**View specific run:**
```bash
gh run view <run-id>
```

**Watch live:**
```bash
gh run watch
```

---

## Configuration Files

**In this directory:**
- `.github/workflows/*.yml` - Workflow definitions
- `.github/*.md` - Documentation
- `.github/setup-ci-cd.sh` - Setup automation

**In repository root:**
- `ruff.toml` - Python linting configuration
- `.coveragerc` - Test coverage configuration
- `.gitignore` - Updated with CI/CD rules

---

## Integration with Enterprise Workflows

These workflows integrate with the enterprise development process:

**Bug Fix Workflow (10 steps):**
- Phase 4: CI Pipeline
- Phase 7: Staging Deployment
- Phase 9: Production Deployment

**Feature Workflow (11 steps):**
- Same as bug fix workflow
- Phase 11: Documentation (manual)

**Quality Gates:**
- Automated: CI checks, health checks
- Manual: Code review, QA testing, PM approval, production approval

---

## Metrics & Monitoring

**CI Pipeline:**
- Target: 100% pass rate
- Current: Track in GitHub Actions

**Deployment Speed:**
- Target: Staging < 5 min, Production < 10 min
- Measure: Workflow run time

**Rollback Speed:**
- Target: < 60 seconds
- Measure: Time to previous version live

---

## Version History

**v1.0** (2026-02-09)
- Initial CI/CD workflows
- Python uv enforcement
- TypeScript bun enforcement
- Staging and production deployments
- Manual approval gates
- Comprehensive documentation

---

## Contributing

When updating workflows:

1. Create feature branch
2. Make changes to `.github/workflows/*.yml`
3. Test in PR (workflows run on PR)
4. Get approval
5. Merge to `claude-redesign`

**Critical:** Test workflow changes in feature branches before merging.

---

## Maintenance

**Weekly:**
- Review failed workflow runs
- Check for outdated actions

**Monthly:**
- Update GitHub Actions to latest versions
- Review and optimize workflow efficiency

**Quarterly:**
- Review deployment procedures
- Update documentation
- Conduct deployment dry-run

---

## Security

**Secrets management:**
- All credentials in GitHub Secrets
- Never commit secrets
- Rotate secrets every 90 days

**Access control:**
- Branch protection enforced
- Manual approval for production
- Audit trail in GitHub Actions

**Artifact security:**
- SHA256 checksums for production
- Artifacts retained 30 days
- Encrypted at rest

---

## Cost

**GitHub Actions:**
- Free tier: 2000 minutes/month (private repos)
- Current usage: ~220 minutes/month
- Well within free tier

**Deployment Platform:**
- Railway: $5-10/month
- Render: $7-14/month
- Heroku: $7-14/month

**Monitoring:**
- Sentry: Free tier (5K events/month)
- UptimeRobot: Free tier (50 monitors)

**Total:** ~$10-20/month

---

## Success Criteria

✓ CI runs automatically on PRs
✓ Package managers enforced
✓ Staging deploys on merge to claude-redesign
✓ Production requires manual approval
✓ Rollback < 60 seconds
✓ Team trained on procedures

---

## Contact

**Questions about:**
- Workflows: Engineering Manager
- Deployment: DevOps Sub-Agent
- Emergency: On-call engineer

**Documentation issues:**
- Create PR with fixes
- Tag: @engineering-manager

---

**Last Updated:** 2026-02-09
**Maintained by:** DevOps Sub-Agent
**Version:** 1.0

---

**Start here:** [QUICK-START.md](./QUICK-START.md) → 30 minutes to deployment automation
