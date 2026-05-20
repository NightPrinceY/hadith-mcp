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

## Do not commit data artifacts

The `data/` directory contains large binary files managed via Git LFS. **Do not include `data/hadith.db` or `data/SHA256SUMS` changes in your PR.** The database is rebuilt by maintainers from the upstream source using the pipeline scripts.

If your change affects the pipeline or schema, describe what the expected DB output change would be in your PR description so maintainers can rebuild and verify.

## Reporting issues

- Search existing issues before opening a new one.
- Include specific examples (collection, hadith number, expected vs actual) for data issues.
- For bugs, include steps to reproduce and your Python version.

## License

By contributing you agree that your contributions will be licensed under GPL-3.0-only, consistent with the project license.
