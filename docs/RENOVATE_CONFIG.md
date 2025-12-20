# Renovate Configuration Guide

This repository uses [Renovate](https://github.com/renovatebot/renovate) for automated dependency updates with security and stability focus.

## Overview

Renovate automatically:
- Creates pull requests for dependency updates
- Groups related updates for easier review
- Prioritizes security updates
- Protects against breaking changes
- Maintains a dependency dashboard

## Configuration Files

- `renovate.json` - Main Renovate configuration
- `.github/renovate.json` - GitHub-specific settings
- `.github/dependabot.yml` - Dependabot backup configuration
- `.github/workflows/dependency-review.yml` - Dependency review workflow

## Key Features

### 1. Security Updates
- **Highest priority** (priority: 10)
- Created immediately (no stability days)
- Labeled with `security`
- Never auto-merged (requires review)

### 2. Dependency Grouping
- **Python dependencies**: Grouped together, scheduled for Monday mornings
- **ML/AI dependencies**: Special handling for PyTorch, transformers, etc.
- **Web framework**: FastAPI, uvicorn, starlette grouped
- **Data processing**: pandas, numpy, scikit-learn grouped

### 3. Auto-merge Strategy
- **Patch updates** for utility packages: Auto-merged after 1 day
- **Minor updates** for safe packages: Auto-merged after 2 days
- **Major updates**: Never auto-merged, require manual review
- **ML/AI dependencies**: Never auto-merged, require careful review

### 4. Stability Protection
- Default: 3 days stability period
- ML/AI dependencies: 7 days
- Major updates: 14 days
- Security updates: 0 days (immediate)

### 5. Special Handling

#### PyTorch CPU Versions
- Pinned to specific version format
- Requires CPU wheel compatibility check
- Labeled with `pytorch`

#### Critical Dependencies
- torch, transformers, google-generativeai, litellm, paper-qa
- Require 7-day stability period
- Never auto-merged
- Assigned to maintainers for review

## Schedule

- **Main schedule**: Monday mornings before 10am UTC
- **Security updates**: At any time (immediate)
- **Lock file maintenance**: First day of each month

## Labels

- `dependencies` - All dependency updates
- `security` - Security-related updates
- `ml`, `ai` - Machine learning dependencies
- `web`, `api` - Web framework dependencies
- `docker` - Docker-related updates
- `github-actions` - CI/CD updates
- `automerge` - Safe to auto-merge
- `major-update` - Breaking changes possible
- `breaking-change` - Known breaking changes

## Dependency Dashboard

Renovate maintains a dependency dashboard issue that shows:
- All pending updates
- Update status
- Grouping information
- Age and adoption metrics

## Review Process

1. **Security updates**: Review immediately
2. **Patch/minor updates**: Review within 3 days
3. **Major updates**: Review within 14 days
4. **ML/AI updates**: Review carefully, test thoroughly

## Auto-merge Safety

Only safe updates are auto-merged:
- Patch updates for utility packages
- Minor updates for well-tested packages
- Never: Major updates, ML/AI dependencies, security updates

## Manual Override

To disable auto-merge for a specific PR:
- Add `[skip-automerge]` to PR title
- Or comment `@renovate ignore` in the PR

## Dependabot Backup

Dependabot is configured as a backup:
- Weekly schedule (Monday 9am)
- Security-focused
- Limited to 10 PRs per ecosystem

## Dependency Review Workflow

### Primary Workflow (Requires GitHub Advanced Security)

The `dependency-review.yml` workflow requires:
- **Dependency graph** enabled
- **GitHub Advanced Security** enabled (for private repositories)

**To enable:**
1. Go to: https://github.com/waldronlab/bioanalyzer-backend/settings/security_analysis
2. Enable "Dependency graph"
3. For private repos, enable "GitHub Advanced Security"

**Note:** This workflow is set to `continue-on-error: true`, so it won't block PRs if Advanced Security is not enabled.

### Alternative Workflow (No Advanced Security Required)

The `dependency-check.yml` workflow provides basic dependency validation:
- Validates requirements.txt format
- Checks Dockerfile for base images
- Provides guidance on enabling full dependency review
- Works without GitHub Advanced Security

Both workflows run automatically on pull requests.

## Best Practices

1. **Review security updates immediately**
2. **Test ML/AI dependency updates thoroughly**
3. **Monitor the dependency dashboard regularly**
4. **Review major updates carefully**
5. **Keep dependencies up to date**

## Troubleshooting

### Renovate not creating PRs
- Check repository settings in GitHub
- Verify Renovate app is installed
- Check `.github/renovate.json` exists

### Too many PRs
- Adjust `prConcurrentLimit` in config
- Increase `stabilityDays` for less frequent updates
- Use grouping to reduce PR count

### Auto-merge not working
- Check package rules match
- Verify stability days have passed
- Check for merge conflicts

## Resources

- [Renovate Documentation](https://docs.renovatebot.com/)
- [Renovate Configuration Options](https://docs.renovatebot.com/configuration-options/)
- [Dependency Dashboard](https://github.com/waldronlab/bioanalyzer-backend/issues)

