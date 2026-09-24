import action_runtime


def test_public_api_exports_expected_symbols() -> None:
    expected = {
        "Action",
        "ActionConfig",
        "Approval",
        "ApprovalDecision",
        "Attempt",
        "ExecutionReceipt",
        "ExecutionStatus",
        "Permission",
        "Recovery",
        "action",
        "execute",
    }

    assert set(action_runtime.__all__) == expected
    for name in expected:
        assert hasattr(action_runtime, name)


def test_package_version_matches_release() -> None:
    assert action_runtime.__version__ == "0.1.0"
