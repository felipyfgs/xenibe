# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python 3.11 experiment lab for Xenibe research. Core code lives under `src/`: `src/forge` provides the CLI entrypoint and response contract, while `src/xenibe` contains backtest, artifacts, candles, execution, metrics, provider, risk, and strategy modules. Tests live in `tests/`, with reusable fixtures under `tests/fixtures/`. Versioned experiment artifacts are stored in `forge/`. Product, CLI, architecture, ADR, and glossary notes are in `docs/`.

## Build, Test, and Development Commands

- Run commands from the repository root.
- `python3 -m pip install -e .` installs the package and local `forge` console script.
- `PYTHONPATH=src python3 -m unittest discover -s tests` runs the standard-library test suite without installing the package first.
- `python3 -m pytest` runs the same tests using the configured `pythonpath` and `testpaths` when pytest is installed.
- `forge init --root forge --json` initializes the local artifact root.
- `forge experiment validate <name> --root forge --json` validates an experiment directory.
- `forge run backtest <name> --root forge --json` runs a backtest and writes immutable run artifacts.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and small functions that match the existing standard-library-first style. Keep imports grouped as standard library, third-party, then local modules. Prefer explicit `pathlib.Path` handling for filesystem work. Experiment names use kebab-case. Run IDs follow `bt-YYYYMMDD-HHMMSS` or `sim-YYYYMMDD-HHMMSS`.

## Testing Guidelines

Tests use `unittest` assertions and may also be collected by pytest. Name test files `test_*.py`, test classes `*Tests`, and test methods `test_*`. Add or update fixture data under `tests/fixtures/` when validating artifact schemas or CLI flows. No coverage threshold is currently enforced. Run `PYTHONPATH=src python3 -m unittest discover -s tests` before handing off changes.

## Commit & Pull Request Guidelines

History uses concise messages such as `feat: add schemas and store for experiment and run artifacts`; prefer imperative commits with a conventional prefix when useful (`feat:`, `fix:`, `test:`). Pull requests should summarize behavior changes, list validation commands run, link related issues or specs, and call out any artifact format changes.

## Security & Configuration Tips

Do not commit secrets, API keys, local Factory or Droid config, `_stude/`, `openspec/`, or `.codex/`. Treat generated artifacts and untracked files as user-owned unless explicitly requested otherwise. Before committing or pushing, inspect `git status --short` and `git diff` for sensitive data.
