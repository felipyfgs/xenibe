# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python 3.11 experiment lab for Xenibe research. Core code lives under `src/`: `src/forge` contains the CLI entrypoint and response contract, while `src/xenibe` contains backtest, artifacts, candles, execution, metrics, provider, risk, and strategy modules. Tests live in `tests/` and fixtures live below `tests/fixtures/`. Versioned experiment artifacts are stored in `forge/`. Product, CLI, architecture, ADR, and glossary notes are in `docs/`.

## Build, Test, and Development Commands

- `python3 -m pip install -e .` installs the package and the `forge` console script locally.
- `python3 -m unittest discover -s tests` runs the current test suite without extra test-runner dependencies.
- `python3 -m pytest` also runs tests using `pyproject.toml` settings when pytest is installed.
- `forge init --root forge --json` initializes the local artifact root.
- `forge experiment validate <name> --root forge --json` validates an experiment directory.
- `forge run backtest <name> --root forge --json` runs a backtest and writes immutable run artifacts.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and small functions that match the existing standard-library-first style. Keep imports grouped as standard library, third-party, then local modules. Prefer explicit `Path` handling for filesystem work. Experiment names use kebab-case, and run IDs follow `bt-YYYYMMDD-HHMMSS` or `sim-YYYYMMDD-HHMMSS`.

## Testing Guidelines

Tests use `unittest` assertions and may be collected by pytest. Name test files `test_*.py`, test classes `*Tests`, and test methods `test_*`. Add or update fixture data under `tests/fixtures/` when validating artifact schemas or CLI flows. Run `python3 -m unittest discover -s tests` before handing off changes.

## Commit & Pull Request Guidelines

History includes short messages such as `feat: add schemas and store for experiment and run artifacts`; prefer concise, imperative commits with a conventional prefix when useful (`feat:`, `fix:`, `test:`). Pull requests should summarize behavior changes, list validation commands run, link related issues or specs, and note any artifact format changes.

## Security & Configuration Tips

Do not commit secrets, API keys, local Factory/Droid config, `_stude/`, `openspec/`, or `.codex/`. Before pushing, inspect `git status --short` and `git diff` for sensitive data.
