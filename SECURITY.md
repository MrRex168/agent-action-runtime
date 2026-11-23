# Security Policy

## Reporting a vulnerability

Please do not open a public issue for a security vulnerability.

Use GitHub's private vulnerability reporting for this repository when available. Include the affected version, reproduction steps, impact, and any suggested mitigation.

## Supported versions

The project is currently pre-1.0. Security fixes target the latest released version.

## Execution safety

Agent Action Runtime can sit in front of side-effecting tools. Treat action implementations, verifiers, approval identities, credentials, and tool arguments as security-sensitive application code. The runtime does not provide a sandbox or credential vault.

An exception, timeout, or failed verification can follow a committed side effect. Enable `retry_safe=True` only if repetition is harmless or the downstream system enforces deduplication for the same logical operation. Supply stable operation keys from trusted application state, and use read-only reconciliation against an authoritative source before confirming success. Treat `needs_review` as an uncertain outcome and check the system of record before issuing another write.

For approval-gated actions, the runtime checks the decision, expiration, action instance, and argument digest. The trusted application must authenticate reviewers, verify they can authorize the exact request, issue time-limited approval records, and configure a validator that checks authoritative records and atomically consumes single-use approvals. The digest and invocation ID are binding data. Authorization comes from the trusted validator. Keep action registration, raw callables, and approval records within the trusted application boundary. Approval checks govern admission to one execution, which may include retries explicitly declared safe.
