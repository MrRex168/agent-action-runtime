# Contributing

Thanks for helping improve Agent Action Runtime.

## Development

Requires Python 3.10+.

```bash
git clone https://github.com/MrRex168/agent-action-runtime.git
cd agent-action-runtime
python -m pip install -e ".[dev]"
pytest
```

## Pull requests

Keep changes focused. Add or update tests for behavior changes and explain any execution-safety tradeoffs in the PR description.

Before opening a PR:

```bash
pytest
python -m build
python -m twine check dist/*
```

## Scope

The project owns the action execution boundary: policy, approval, execution, retry, verification, recovery, and receipts.

Please avoid expanding the core into an agent framework, workflow engine, memory layer, observability platform, or sandbox without prior discussion.
