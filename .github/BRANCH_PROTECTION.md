# Branch Protection Configuration Guide

This document describes the recommended branch protection rules for the BioAnalyzer Backend repository.

## Protected Branches

The following branches should be protected:
- `main` (production)
- `develop` (development)

## Recommended Branch Protection Settings

### 1. Require Pull Request Reviews

- **Required approvals**: 1 (minimum)
- **Dismiss stale pull request approvals when new commits are pushed**: ✅ Enabled
- **Require review from Code Owners**: ✅ Enabled (if CODEOWNERS file exists)
- **Restrict who can dismiss pull request reviews**: ✅ Enabled (repository admins only)

### 2. Require Status Checks to Pass

**Required status checks:**
- ✅ `Test Python 3.11` (from `ci.yml`)
- ✅ `Lint Code` (from `ci.yml`)
- ✅ `Type Check` (from `ci.yml`)
- ✅ `Security Scan` (from `ci.yml`)
- ✅ `Docker Build Test` (from `ci.yml`)
- ✅ `All Checks Summary` (from `ci.yml`)
- ✅ `Validate Pull Request` (from `pr-validation.yml`)
- ✅ `Code Quality Analysis` (from `code-quality.yml`)
- ✅ `Security Vulnerability Scan` (from `security-scan.yml`)

**Settings:**
- ✅ Require branches to be up to date before merging
- ✅ Do not allow bypassing the above settings

### 3. Require Conversation Resolution Before Merging

- ✅ Require all conversations on code to be resolved before merging

### 4. Require Linear History

- ✅ Require linear history (prevents merge commits, enforces rebase/squash)

### 5. Require Signed Commits (Optional but Recommended)

- ⚠️ Require signed commits (if GPG signing is enabled)

### 6. Require Admin Review (Optional)

- ⚠️ Include administrators (recommended for critical branches)

### 7. Restrict Who Can Push to Matching Branches

- ✅ Restrict pushes that create matching branches
- **Allowed**: Repository admins and maintainers only

## How to Configure

1. Go to: `https://github.com/waldronlab/bioanalyzer-backend/settings/branches`
2. Click "Add rule" or edit existing rule
3. Configure the settings above
4. Save changes

## Workflow Integration

The CI/CD workflows are designed to work with these branch protection rules:

- **`ci.yml`**: Main CI pipeline with tests, linting, type checking, security, and Docker build
- **`pr-validation.yml`**: Validates PR title, commit messages, large files, sensitive data
- **`code-quality.yml`**: Additional code quality checks
- **`security-scan.yml`**: Comprehensive security scanning

All workflows must pass before a PR can be merged.

## Bypassing Protection (Emergency Only)

In emergency situations, repository admins can:
1. Temporarily disable branch protection
2. Make the necessary changes
3. Re-enable branch protection immediately

**Note**: This should be documented in the commit message and reviewed in the next team meeting.

## Status Check Requirements

The following status checks are **required** and **cannot be bypassed**:

### Critical (Must Pass)
- ✅ Tests must pass
- ✅ Code must be properly formatted (black)
- ✅ Code must pass linting (flake8)
- ✅ Security scans must pass
- ✅ Docker build must succeed

### Important (Should Pass)
- ✅ Type checking (mypy)
- ✅ PR validation
- ✅ Code quality analysis

### Informational (Warnings Only)
- ⚠️ Code complexity warnings
- ⚠️ Dependency audit warnings

## Coverage Requirements

- **Minimum test coverage**: 60%
- Coverage is enforced in the test job with `--cov-fail-under=60`

## Security Requirements

- **No critical or high severity vulnerabilities** in dependencies
- **No hardcoded secrets** in code
- **All security scans must pass**

## Documentation Requirements

- PRs should include:
  - Clear description of changes
  - Testing instructions (if applicable)
  - Breaking changes documented
  - Migration guide (if applicable)

## Enforcement

These rules are enforced through:
1. GitHub branch protection settings
2. Required status checks in CI/CD workflows
3. PR validation workflow
4. Code review requirements

## Questions?

If you have questions about branch protection or need exceptions:
- Contact repository administrators
- Open an issue for discussion
- Review the [CONTRIBUTING.md](../CONTRIBUTING.md) guide

