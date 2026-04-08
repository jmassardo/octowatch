# Security Policy

## Reporting a Vulnerability

**Please do not open public issues for security vulnerabilities.**

If you discover a security vulnerability in OctoWatch, we appreciate your help in disclosing it responsibly.

### Preferred: GitHub Security Advisories

Report vulnerabilities through [GitHub Security Advisories](https://github.com/octowatch/octowatch/security/advisories/new). This allows us to collaborate on a fix privately before public disclosure.

### Alternative: Issue

If you are unable to use Security Advisories, you can open a [regular issue](https://github.com/octowatch/octowatch/issues/new) with the label **security**. Please include:

- A description of the vulnerability
- Steps to reproduce the issue
- The potential impact
- Any suggested fixes (if applicable)

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.x (latest) | :white_check_mark: |
| Older releases | :x: |

Only the latest release receives security updates. We recommend always running the most recent version.

## Disclosure Timeline

- **Acknowledgment:** We will acknowledge receipt of your report within **48 hours**.
- **Assessment:** We will assess the severity and impact and provide an initial response within **5 business days**.
- **Fix Target:** We aim to develop and release a fix within **90 days** of the initial report, depending on complexity.
- **Disclosure:** We will coordinate public disclosure with you after the fix is released. If you do not hear back within 48 hours, please follow up.

## Security Update Policy

Security fixes are released as patch versions (e.g., 0.1.1) and announced through:

- GitHub Releases with security advisory references
- The [CHANGELOG.md](CHANGELOG.md)

We recommend subscribing to GitHub release notifications to stay informed about security updates.

## Scope

The following are in scope for security reports:

- The OctoWatch backend API (FastAPI application)
- The OctoWatch frontend (React application)
- Docker and Helm deployment configurations
- Authentication and authorization logic (OAuth, SAML, RBAC)
- Data handling and storage (audit events, credentials)

The following are **out of scope**:

- Vulnerabilities in upstream dependencies (report these to the respective projects)
- Issues in user-managed infrastructure (your database, your network)
- Social engineering attacks against OctoWatch maintainers
