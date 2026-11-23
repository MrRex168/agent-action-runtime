import asyncio
import time
from dataclasses import replace

import pytest

from action_runtime import Approval, ApprovalDecision, ExecutionStatus, action, execute


@pytest.mark.asyncio
async def test_approval_binds_arguments_and_action_identity() -> None:
    calls = []
    validation_calls = []

    def validate(candidate: Approval) -> bool:
        validation_calls.append(candidate)
        return candidate == issued

    def write(record: dict, mode: str = "create") -> str:
        calls.append((record, mode))
        return mode

    approved_action = action(name="write", permission="ask", approval_validator=validate)(write)
    other_action = action(name="write", permission="ask", approval_validator=validate)(write)
    record = {"id": 7, "active": True}
    request = approved_action.approval_request(record)
    assert request.invocation_id != approved_action.approval_request(record).invocation_id
    issued = Approval(ApprovalDecision.APPROVE, request=request, expires_at=time.time() + 60)

    for candidate, args in (
        (approved_action, ({"id": 8, "active": True},)),
        (approved_action, ({"active": True, "id": 7},)),
        (approved_action, ({"id": 7, "active": True}, "replace")),
        (other_action, (record,)),
    ):
        rejected = await execute(candidate, *args, approval=issued)
        assert rejected.status is ExecutionStatus.DENIED
        assert rejected.attempts == 0
    assert validation_calls == []
    assert calls == []

    receipt = await execute(approved_action, record=record, mode="create", approval=issued)
    assert receipt.status is ExecutionStatus.SUCCESS
    assert receipt.approval == issued
    assert calls == [(record, "create")]
    assert validation_calls == [issued]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["approve", "invalid", None, True])
async def test_malformed_approval_decisions_fail_closed(decision) -> None:
    def unexpected_validator(approval: Approval) -> bool:
        pytest.fail("Malformed approval reached the validator")

    @action(permission="ask", approval_validator=unexpected_validator)
    def write() -> None:
        pytest.fail("Malformed approval authorized execution")

    approval = Approval(decision, request=write.approval_request(), expires_at=time.time() + 60)
    receipt = await execute(write, approval=approval)
    assert receipt.status is ExecutionStatus.DENIED
    assert receipt.attempts == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("expires_at", [0, None, float("nan"), float("inf")])
async def test_expired_or_invalid_expiration_fails_closed(expires_at) -> None:
    def unexpected_validator(approval: Approval) -> bool:
        pytest.fail("Invalid expiration reached the validator")

    @action(permission="ask", approval_validator=unexpected_validator)
    def write() -> None:
        pytest.fail("Invalid expiration authorized execution")

    receipt = await execute(
        write,
        approval=Approval(ApprovalDecision.APPROVE, request=write.approval_request(), expires_at=expires_at),
    )
    assert receipt.status is ExecutionStatus.DENIED
    assert receipt.attempts == 0


@pytest.mark.asyncio
async def test_bound_approval_requires_an_application_validator() -> None:
    @action(permission="ask")
    def write() -> None:
        pytest.fail("An unauthenticated approval authorized execution")

    approval = Approval(
        ApprovalDecision.APPROVE, request=write.approval_request(), expires_at=time.time() + 60,
    )
    assert (await execute(write, approval=approval)).status is ExecutionStatus.DENIED


@pytest.mark.asyncio
async def test_trusted_store_validates_and_consumes_approval_once() -> None:
    pending = {}
    lock = asyncio.Lock()
    writes = []

    async def validate(candidate: Approval) -> bool:
        async with lock:
            key = candidate.request.invocation_id
            if pending.get(key) != candidate or candidate.expires_at <= time.time():
                return False
            del pending[key]
            return True

    @action(permission="ask", approval_validator=validate)
    async def write(record: str) -> None:
        await asyncio.sleep(0)
        writes.append(record)

    request = write.approval_request("approved record")
    issued = Approval(
        ApprovalDecision.APPROVE, by="reviewer", request=request, expires_at=time.time() + 60,
    )
    pending[request.invocation_id] = issued
    forged = replace(issued, by="another reviewer")
    assert (await execute(write, "approved record", approval=forged)).status is ExecutionStatus.DENIED

    receipts = await asyncio.gather(
        execute(write, "approved record", approval=issued),
        execute(write, "approved record", approval=issued),
    )
    assert {r.status for r in receipts} == {ExecutionStatus.SUCCESS, ExecutionStatus.DENIED}
    assert writes == ["approved record"]


@pytest.mark.asyncio
async def test_approval_uses_snapshot_across_validation_and_retries() -> None:
    record = {"id": 7}
    writes = []

    async def validate(candidate: Approval) -> bool:
        await asyncio.sleep(0)
        record["id"] = 8
        return candidate == issued

    @action(permission="ask", approval_validator=validate, retry_safe=True, retries=1)
    def write(value: dict) -> None:
        writes.append(value["id"])
        value["id"] = 9
        if len(writes) == 1:
            raise ConnectionError("retry")

    issued = Approval(
        ApprovalDecision.APPROVE, request=write.approval_request(record), expires_at=time.time() + 60,
    )
    receipt = await execute(write, record, approval=issued)
    assert receipt.status is ExecutionStatus.SUCCESS
    assert writes == [7, 7]


@pytest.mark.parametrize("permission", ["ask", "deny"])
def test_direct_calls_cannot_skip_policy(permission: str) -> None:
    @action(permission=permission)
    def write() -> None:
        pytest.fail("Direct call bypassed policy")

    with pytest.raises(PermissionError, match="execute"):
        write()


@pytest.mark.asyncio
async def test_approval_that_expires_during_validation_is_denied(monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("action_runtime.executor.time.time", lambda: clock[0])

    async def validate(candidate: Approval) -> bool:
        await asyncio.sleep(0)
        clock[0] = 101.0
        return True

    @action(permission="ask", approval_validator=validate)
    def write() -> None:
        pytest.fail("Expired approval authorized execution")

    approval = Approval(
        ApprovalDecision.APPROVE, request=write.approval_request(), expires_at=101.0,
    )
    receipt = await execute(write, approval=approval)
    assert receipt.status is ExecutionStatus.DENIED
    assert receipt.attempts == 0
