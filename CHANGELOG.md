# Changelog

## v0.2.0

Suggested GitHub release title: **Agent Action Runtime v0.2.0 — Safer Retries, Approvals, and Tool Receipts**

- Execution receipts reflect the final attempt. Verification state is recorded explicitly, and successful attempts without a verifier use `verified=None` in history. [PR #10](https://github.com/MrRex168/agent-action-runtime/pull/10)
- Automatic retries require an explicit safety declaration. An optional read-only reconciliation callback can confirm uncertain outcomes before any replay. [PR #11](https://github.com/MrRex168/agent-action-runtime/pull/11)
- Human approvals bind to a specific invocation, registered action instance, and argument snapshot. A trusted application validator checks the issued record and can atomically consume it. [PR #12](https://github.com/MrRex168/agent-action-runtime/pull/12)
- OpenAI tool receipts expose bounded metadata and fixed error codes, with opt-in projection of selected successful results. Applications retain full receipts from `execute()`. [PR #13](https://github.com/MrRex168/agent-action-runtime/pull/13)
- Caller cancellation propagates during timed calls. Runtime deadlines are distinguished from downstream timeouts, and the SDK uses a generic response if receipt generation fails.

### Upgrading from v0.1.0

1. **Retries.** Audit every `retries=N` declaration. Add `retry_safe=True` only where replay is harmless or the downstream system enforces deduplication. Pass a stable application-generated operation key if the downstream guarantee depends on it. An unresolved outcome without an explicit safety declaration returns `needs_review` after one attempt, including under `on_failure="fail"`. Reconcile against an authoritative system before issuing another write. An action deadline or cancelled call may follow a remote commit.
2. **Approvals.** Replace bare approvals and string shorthand with `Action.approval_request()`, an issued `Approval` with a finite expiration, and a configured `approval_validator`. Pass plain JSON values and preserve dictionary order. Existing pending records must be reissued, including after action re-registration or restart. Use `execute()` for policy-gated actions. Direct calls to `ask` and `deny` actions raise `PermissionError`. The application authenticates reviewers, checks their authority, validates full issued records, and atomically consumes single-use approvals.
3. **OpenAI tool receipts.** Read `status` and `error_code` in place of parsing raw messages. Default tool output omits `error`, `history`, `approval`, `duration_ms`, and `result`. Configure `result_projection` only for selected fields suitable for the model. Invalid and oversized projections are omitted, and a generic SDK tool error means the execution outcome is unknown. Keep diagnostics inside the trusted application.
4. **Receipt interpretation.** A failed final invocation carries no result from an earlier attempt. Successful history entries without a verifier now use `verified=None`. An expired runtime deadline stays a timeout even when async cleanup returns a late value.

### Maintainer release checklist

- [ ] Review and merge the release-readiness PR after Python 3.10–3.12, packaging, and SDK checks pass.
- [ ] Verify the candidate version is `0.2.0` in both a clean wheel installation and distribution metadata. Confirm the wheel and source distribution pass `twine check`.
- [ ] Run the offline CRM demo and the SDK contract test without a model call. Run the live OpenAI demo if credentials and a live check are available.
- [ ] Review the migration notes and confirm the intended tagged commit is on `main`.
- [ ] When ready to publish, create and push `v0.2.0` at that commit. The tag triggers the existing GitHub release workflow.
- [ ] Confirm the release workflow attached the wheel and source distribution. Set the release title above, include the release highlights and migration notes, and smoke-test installation from the tag.
