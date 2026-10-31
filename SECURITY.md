# Security Policy

## Supported Versions

Only the latest release of `casambi-classic-ble` is actively supported for security updates and bug fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |
| < 0.3.0 | :x:                |

---

## Reporting a Vulnerability

The maintainers take security seriously, especially given that this library handles Bluetooth Low Energy mesh communications, cryptographic network keys, and authentication hashes.

If you discover a security vulnerability or sensitive data exposure issue, **please DO NOT open a public GitHub issue**.

### Preferred Reporting Method
Report vulnerabilities privately through one of the following channels:

1. **GitHub Private Vulnerability Reporting:**
   Use GitHub's built-in [Advisories / Report a Vulnerability](https://github.com/hellqvio86/casambi-classic-ble/security/advisories/new) tab.
2. **Direct Maintainer Contact:**
   Email the lead maintainer directly at:  
   **`olof.hellqvist@gmail.com`**  
   *Please include "[SECURITY] casambi-classic-ble" in the subject line.*

### Response SLAs
- **Initial Acknowledgment:** Within **48 hours** of report receipt.
- **Triage & Assessment:** Within **5 business days** with status and severity assessment.
- **Remediation & Patch Release:** Critical vulnerabilities will be addressed in a patch release published to PyPI and GitHub within **14 business days** or coordinated via private advisory.

---

## Zero PII & Network Key Protection Mandate

Users, contributors, and bug reporters must adhere to strict data hygiene guidelines:

> [!CAUTION]
> **Never post real credentials, network passwords, encryption keys, or real Bluetooth MAC addresses in public issues, discussions, pull requests, or logs.**

When submitting bug reports, Wireshark BTSnoop captures, or debug logs:
- **Redact all network passwords and authentication hashes** (`AUTHENTICATE` payload).
- **Mask real MAC addresses** with generic placeholders (e.g., `AA:BB:CC:DD:EE:FF` or `00:11:22:33:44:55`).
- **Redact custom device names and location tags** that identify physical premises or occupants.

All automated commits to this repository are scanned with [TruffleHog](https://github.com/trufflesecurity/trufflehog) in pre-commit hooks and GitHub Actions CI.
