# Repository Guidelines

## Project Structure & Module Organization

This repository is a Python 3.11 experiment lab for Xenibe research. Core code lives under `src/`: `src/forge` implements the `forge` CLI, command routing, JSON response contract, and command modules, while `src/xenibe` contains analysis, artifact, backtest, candle, execution, metrics, provider, risk, and strategy code. Tests live in `tests/`, with reusable fixtures under `tests/fixtures/`. Local experiment roots are created with `forge init --root forge --json`; treat generated artifacts as user-owned unless a task explicitly asks to modify them.

## Build, Test, and Development Commands

- Run commands from the repository root.
- `python3 -m pip install -e .` installs the package and local `forge` console script.
- `PYTHONPATH=src python3 -m unittest discover -s tests` runs the full standard-library test suite without installing first.
- `python3 -m pytest` runs the same suite through pytest using `pyproject.toml` configuration when pytest is installed.
- `forge init --root forge --json` initializes the local artifact root.
- `forge experiment validate <name> --root forge --json` validates an experiment directory.
- `forge run backtest <name> --root forge --json` runs a backtest and writes immutable run artifacts.

## Coding Style & Naming Conventions

Use 4-space indentation, type hints, and small functions that match the existing standard-library-first style. Keep imports grouped as standard library, third-party, then local modules. Prefer explicit `pathlib.Path` handling for filesystem work. CLI commands should return structured responses through the existing response helpers. Experiment names use kebab-case. Run IDs follow `bt-YYYYMMDD-HHMMSS`.

## Testing Guidelines

Tests use `unittest` assertions and may also be collected by pytest. Name test files `test_*.py`, test classes `*Tests`, and test methods `test_*`. Add or update fixture data under `tests/fixtures/` when validating artifact schemas, CLI flows, or run outputs. No coverage threshold is currently enforced. Run `PYTHONPATH=src python3 -m unittest discover -s tests` before handing off changes.

## Commit & Pull Request Guidelines

History uses concise messages such as `feat: add status command and service for inspecting project state`; prefer imperative commits with a conventional prefix when useful (`feat:`, `fix:`, `test:`). Pull requests should summarize behavior changes, list validation commands run, link related issues or specs, and call out any artifact format changes.

## Security & Configuration Tips

Do not commit secrets, API keys, `_stude/`, `openspec/`, `.opencode/`, `.env`, or virtual environments. Treat generated artifacts and untracked files as user-owned unless explicitly requested otherwise. Before committing or pushing, inspect `git status --short`, staged diffs, and relevant config files for sensitive data.

## OpenSpec & Spec Language

Write all new or updated OpenSpec artifacts in Brazilian Portuguese (pt-BR), including `proposal.md`, `design.md`, `tasks.md`, delta specs, and main specs. Keep OpenSpec-required structural tokens in English when needed for validation, such as `## ADDED Requirements`, `## MODIFIED Requirements`, `### Requirement:`, `#### Scenario:`, `WHEN`, `THEN`, `AND`, and `SHALL`. Preserve code identifiers, CLI commands, schema keys, artifact names, provider names, and error codes exactly as implemented. When touching existing English specs, translate the edited sections to pt-BR when practical, but do not mass-translate unrelated historical artifacts unless explicitly requested.

## Agent-Specific Instructions

Always communicate with the user in Brazilian Portuguese (pt-BR), unless the user explicitly requests another language.
