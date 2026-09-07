# Contributing

Issues and pull requests are welcome.

## Development

1. Create a Python 3.10+ virtual environment.
2. Install dependencies with `python -m pip install -r requirements-dev.txt`.
3. Run `python -m unittest discover -s tests -q`.
4. Run `python -m compileall -q usage_monitor_for_codex`.
5. Run `python -m pyright`.

Keep changes focused, add tests for behavior changes, and do not include credential files, account data, build output, or local settings. Windows executable changes should also be verified with `python build.py`.

By contributing, you agree that your contribution is provided under the repository's MIT license.
