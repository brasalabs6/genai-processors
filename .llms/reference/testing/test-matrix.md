# Test Matrix

Use the smallest validation that covers the change, then expand when touching
shared contracts.

## Source References

- CI matrix, install, lint, and pytest commands:
  `.github/workflows/python-tests.yml:16-42`
- Development dependencies: `pyproject.toml:63-77`
- Blocking flake8 config in CI: `.github/workflows/python-tests.yml:33-39`
- MkDocs config: `documentation/mkdocs.yml:1-90`
- Docs deploy command: `.github/workflows/deploy_docs.yml:22-32`
- Test suites: `genai_processors/tests/`, `genai_processors/contrib/tests/`

## CI Baseline

CI installs:

```bash
python -m pip install --upgrade pip
pip install .
pip install .[contrib]
pip install .[dev]
```

Then runs:

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=500 --indent-size=2 --statistics
pytest
```

The CI matrix is Python `3.11`, `3.12`, and `3.13`.

## Local Test Commands

Run all tests:

```bash
pytest
```

Run one test file:

```bash
pytest genai_processors/tests/processor_test.py
```

Run contrib tests:

```bash
pytest genai_processors/contrib/tests
```

Run a focused keyword selection:

```bash
pytest -k "processor or streams"
```

Run syntax/undefined-name lint matching the blocking CI lint:

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
```

Run advisory lint matching CI:

```bash
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=500 --indent-size=2 --statistics
```

## Docs-Only Validation

Use this when only Markdown or docs navigation changed:

```bash
python -m pip install mkdocs-material mkdocs-include-markdown-plugin
cd documentation
mkdocs build --strict
```

If the changed docs are outside `documentation/docs/`, also check links and
source references manually because MkDocs may not include them.

## Change-To-Test Mapping

- `content_api.py`: run `genai_processors/tests/content_api_test.py` plus any
  MIME-specific tests.
- `processor.py`: run `genai_processors/tests/processor_test.py`,
  `genai_processors/tests/map_processor_test.py`, and focused tests for changed
  composition behavior.
- `streams.py`: run `genai_processors/tests/streams_test.py` and any processor
  tests that consume split, concat, or merge.
- `genai_processors/core/*`: run the matching test file under
  `genai_processors/tests/` and any integration tests for that processor.
- `genai_processors/contrib/*`: run matching tests under
  `genai_processors/contrib/tests/` and install with `pip install .[contrib]`.
- Packaging metadata: run installation checks and at least the CI lint command.
- MkDocs navigation or docs pages: run docs-only validation.
- `llms.txt`: no automated owner exists in CI; review against
  `content_api.py`, `processor.py`, and examples manually.
