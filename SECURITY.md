# Security Policy

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

If you discover a security vulnerability in OctoWatch, please report it through one of the following channels:

1. **GitHub Security Advisories** (preferred): [Report a vulnerability](https://github.com/octowatch/octowatch/security/advisories/new)
2. **Email**: security@octowatch.dev

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix target**: Within 90 days (severity-dependent)

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Security Update Policy

Security patches are released as soon as possible after a fix is verified. Critical vulnerabilities may trigger an out-of-band release.

## Security Best Practices for Deployers

- Always use TLS in production (never disable HTTPS redirect)
- Rotate `SECRET_KEY` periodically
- Use External Secrets Operator or Sealed Secrets for Kubernetes deployments
- Restrict database access to application service accounts only
- Enable audit trail logging and review regularly
- Keep dependencies updated (Dependabot is configured for this repository)
