# Deployment Checklist

Complete this checklist before each production deployment.

---

## Pre-Deployment (Phase 1-6)

### Development Complete
- [ ] Feature/bug fix implemented
- [ ] Code committed to feature branch
- [ ] All local tests pass

### Code Quality (Phase 4)
- [ ] CI pipeline passes all checks
- [ ] Linting errors resolved (ruff)
- [ ] Type checking passes (mypy)
- [ ] Test coverage ≥80%
- [ ] No critical security vulnerabilities

### Code Review (Phase 5)
- [ ] PR created to `claude-redesign` branch
- [ ] Code review completed by senior engineer
- [ ] All review feedback addressed
- [ ] PR approved and merged

### QA Testing (Phase 6)
- [ ] Test plan created
- [ ] Manual testing completed
- [ ] Edge cases tested
- [ ] Performance acceptable
- [ ] QA sign-off received

---

## Staging Deployment (Phase 7)

### Pre-Staging
- [ ] All Phase 1-6 items complete
- [ ] Environment variables configured
- [ ] Staging database ready
- [ ] Deployment platform configured

### Staging Deployment
- [ ] PR merged to `claude-redesign` branch
- [ ] Staging deployment triggered automatically
- [ ] Deployment completed successfully
- [ ] No errors in deployment logs

### Staging Verification
- [ ] Health check endpoint returns 200
- [ ] Application accessible at staging URL
- [ ] Core functionality works
- [ ] API endpoints responding correctly
- [ ] Database migrations applied
- [ ] No error spikes in Sentry

### Smoke Tests
- [ ] User can access application
- [ ] Authentication works (if applicable)
- [ ] Core features functional
- [ ] Performance within acceptable range
- [ ] No JavaScript errors in console

---

## PM Review (Phase 8)

### PM Testing
- [ ] PM has staging URL
- [ ] PM tested all new features
- [ ] PM verified bug fixes
- [ ] PM tested edge cases
- [ ] PM checked user experience

### PM Approval
- [ ] PM approves feature/fix
- [ ] PM approves for production deployment
- [ ] PM signs off on release notes
- [ ] PM confirms timing acceptable

---

## Production Deployment (Phase 9)

### Pre-Production
- [ ] All Phase 1-8 items complete
- [ ] Staging tested for at least 24 hours
- [ ] No critical issues in staging
- [ ] Production environment variables set
- [ ] Database backup completed
- [ ] Rollback plan documented

### Timing Check
- [ ] NOT Friday afternoon (unless urgent)
- [ ] NOT weekend (unless urgent)
- [ ] NOT during peak hours
- [ ] On-call engineer available
- [ ] Team available for monitoring

### Production PR
- [ ] PR created from `claude-redesign` to `main`
- [ ] PR description includes changes summary
- [ ] PR includes testing evidence
- [ ] PR includes rollback instructions
- [ ] At least 2 approvals (including PM)
- [ ] PR merged to `main` branch

### Manual Approval Gate
- [ ] Production deployment workflow triggered
- [ ] Deployment waiting for approval
- [ ] PM/EM/Abbe reviews deployment
- [ ] Approver verifies all phases complete
- [ ] Deployment approved in GitHub

### Production Deployment
- [ ] Deployment started
- [ ] Deployment completed successfully
- [ ] Release tag created
- [ ] No errors in deployment logs

### Production Verification
- [ ] Health check endpoint returns 200
- [ ] Application accessible at production URL
- [ ] Core functionality works
- [ ] API endpoints responding
- [ ] Database migrations applied
- [ ] SSL/HTTPS working

### Post-Deployment
- [ ] No error spikes in Sentry
- [ ] Response times normal
- [ ] Server resources normal (CPU, memory)
- [ ] Monitoring dashboards show healthy status
- [ ] No user complaints

---

## Post-Deployment Monitoring

### Immediate (0-30 minutes) - CRITICAL
- [ ] Active monitoring of error rates
- [ ] Active monitoring of response times
- [ ] Checking logs for anomalies
- [ ] Watching user activity
- [ ] Ready to rollback if needed

### Short-term (30 minutes - 4 hours)
- [ ] Periodic check of error rates
- [ ] Periodic check of performance metrics
- [ ] Review user feedback/reports
- [ ] Monitor system resources

### Medium-term (4-24 hours)
- [ ] Daily metrics review
- [ ] User feedback analysis
- [ ] Performance trend analysis
- [ ] Error rate trending

### Long-term (24+ hours)
- [ ] Weekly metrics review
- [ ] Cost analysis (if applicable)
- [ ] Plan next deployment

---

## Emergency Rollback (If Needed)

### Trigger Conditions
- [ ] Error rate > 5%
- [ ] Service down > 2 minutes
- [ ] Critical functionality broken
- [ ] Data corruption detected
- [ ] Security breach detected

### Rollback Steps
```bash
# 1. Trigger rollback
[platform-specific rollback command]

# 2. Verify rollback successful
curl https://darin-app.example.com/health

# 3. Notify team
# Post in Slack/email

# 4. Create incident report
# Document what went wrong

# 5. Plan fix
# Schedule follow-up deployment
```

### Rollback Verification
- [ ] Previous version deployed
- [ ] Health check passing
- [ ] Error rates normal
- [ ] Users can access application
- [ ] Team notified of rollback

---

## Documentation (Phase 11 - Features Only)

### Update Documentation
- [ ] README.md updated
- [ ] CHANGELOG.md updated
- [ ] API documentation updated (if applicable)
- [ ] User documentation updated
- [ ] Deployment notes added

### Release Notes
- [ ] Create release notes
- [ ] Summarize new features
- [ ] List bug fixes
- [ ] Document breaking changes
- [ ] Publish to team/users

---

## Sign-Off

**Feature/Bug:** [Name/ID]

**Deployed by:** _______________________

**Date/Time:** _______________________

**Release Version:** _______________________

**PM Approval:** _______________________ (Signature)

**EM Approval:** _______________________ (Signature)

**Deployment Status:** [ ] Success [ ] Failed [ ] Rolled Back

**Notes:**
```
[Any additional notes about the deployment]
```

---

## Troubleshooting Quick Reference

### CI Pipeline Failed
1. Check GitHub Actions logs
2. Run checks locally: `ruff check .`, `mypy .`, `pytest`
3. Fix errors and push

### Staging Deployment Failed
1. Check deployment logs in GitHub Actions
2. Verify secrets configured correctly
3. Check platform-specific logs
4. Fix issues and push to `claude-redesign`

### Production Deployment Failed
1. **DO NOT PANIC**
2. Check deployment logs
3. If critical: Trigger rollback immediately
4. Investigate root cause
5. Fix and plan redeployment

### Rollback Needed
1. Navigate to GitHub Actions
2. Find previous successful deployment
3. Trigger rollback via platform
4. Verify rollback successful
5. Communicate to team
6. Create incident report

---

**Version:** 1.0
**Last Updated:** 2026-02-09
**Maintained by:** DevOps Sub-Agent
