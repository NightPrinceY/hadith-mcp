# Contributing

Thanks for your interest in contributing to hadith-mcp.

## Getting started

```bash
git clone https://github.com/ovehbe/hadith-mcp.git
cd hadith-mcp
uv run --python 3.12 --extra dev pytest -q
```

## Guidelines

- Keep PRs focused — one logical change per PR.
- Match existing code style. Run `ruff check` and `ruff format --check` before submitting.
- Run `pytest` and ensure all tests pass.
- Write tests for new logic when practical.

## Data directory

The `data/` directory is gitignored — it contains generated artifacts (`hadith.db`, checkpoints, etc.) that are built locally via the pipeline scripts. See `data/README.md` for build instructions.

**Never commit database files or other generated data.** If your change affects the pipeline or schema, describe the expected output change in your PR description so maintainers can rebuild and verify.

## Reporting issues

- Search existing issues before opening a new one.
- Include specific examples (collection, hadith number, expected vs actual) for data issues.
- For bugs, include steps to reproduce and your Python version.

## License

By contributing you agree that your contributions will be licensed under GPL-3.0-only, consistent with the project license.
