# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.4   | ✅ Yes             |
| < 0.1.4 | ⚠️ Not maintained   |

## Reporting a Vulnerability

**DO NOT** open a public issue for security vulnerabilities.

Please report security issues privately to the maintainers:

1. **Email**: Contact the project maintainers directly
2. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce (if applicable)
   - Potential impact
   - Suggested fix (if you have one)

We will:
- Acknowledge receipt within 48 hours
- Investigate and assess the severity
- Work on a fix and release a patch
- Credit you in the security advisory (if desired)

## Security Considerations

### Cryptography
- We use **Ed25519** for signature verification
- All memory commits are cryptographically signed
- Blob integrity is verified via decompression checks

### Data Privacy
- **PII Scanner** detects and flags sensitive information
- **Privacy Budget** implements differential privacy constraints
- **Encryption** available for sensitive memory stores

### Access Control
- **Access Index** tracks who/when memories are accessed
- **Trust Framework** validates federated partners
- **Audit Logs** maintain immutable operation records

## Best Practices

When using agmem in production:

1. **Keep dependencies updated**
   ```bash
   pip install --upgrade agmem
   ```

2. **Enable encryption** for sensitive data
   ```bash
   agmem config set encryption.enabled true
   ```

3. **Configure privacy budget** appropriately
   ```bash
   agmem config set privacy.epsilon 1.0
   ```

4. **Monitor audit logs** regularly
   ```bash
   agmem audit --since "7 days ago"
   ```

5. **Review access patterns** periodically
   ```bash
   agmem access-index --user <user_id>
   ```

## Dependencies

agmem uses the following key dependencies:
- `PyYAML` - Configuration parsing
- `cryptography` - Encryption support (optional)
- `typing-extensions` - Type hints

We monitor these for vulnerabilities and issue patches promptly.

## Incident Response

In case of a confirmed vulnerability:

1. We will release a patch version immediately
2. Security advisories will be published on GitHub
3. Users will be notified via PyPI and changelog
4. The CVE process will be initiated if appropriate

## Questions?

For security-related questions or clarifications, contact the maintainers directly.
