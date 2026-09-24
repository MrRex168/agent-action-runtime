# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability.

Use GitHub's private vulnerability reporting for this repository when available. Include the affected version, reproduction steps, impact, and any suggested mitigation.

## Supported versions

The project is currently pre-1.0. Security fixes target the latest released version.

## Execution safety

Agent Action Runtime can sit in front of side-effecting tools. Treat action implementations, verifiers, approval identities, credentials, and tool arguments as security-sensitive application code. The runtime does not provide a sandbox or credential vault.
