# Repository Guidelines

## Project Structure & Module Organization
`main.py` is the plugin entrypoint and registers commands plus platform adapters. Keep public integration points in `public_api.py`; other modules should prefer that surface over deep imports. Core runtime logic lives in `runtime/` (event parsing, sending, token management, template loading), platform wiring lives in `adapters/`, and persistence lives in `db/` (`models.py`, `repository.py`, `service.py`). Stateless QQ API helpers remain in `core/qq/`. Shared templates belong in `templates/` with `templates/registry.yaml`. `wanbot/` is an optional private extension area; avoid coupling public code to it unless the feature is explicitly private.

## Build, Test, and Development Commands
This plugin is loaded by AstrBot rather than built as a standalone package.

- `python3 -m compileall .` checks Python syntax across the plugin.
- `find . -name '*.py' -exec python3 -c "import ast; ast.parse(open('{}').read())" \\;` performs a lightweight AST parse pass.
- `python3 -c "import json; json.load(open('_conf_schema.json')); print('OK')"` validates the config schema file.

For functional verification, install the repo under `<AstrBot>/data/plugins/qq_restapi` and restart AstrBot to exercise the WebSocket or Webhook adapter.

## Coding Style & Naming Conventions
Use 4-space indentation, type hints where practical, `snake_case` for modules/functions, and `PascalCase` for classes. Match the existing Python style in `main.py` and `runtime/`. Keep adapter code focused on transport concerns; business logic belongs in `runtime/` or `db/`. When adding plugin config, update both `[_conf_schema.json](_conf_schema.json)` and `_PLUGIN_CONFIG_KEYS` in `runtime/context.py`.

## Testing Guidelines
There is no dedicated `tests/` directory yet. Treat syntax checks plus AstrBot smoke testing as the minimum bar. If you add behavior with branching logic, include a focused validation path in docs or a reproducible command example. Prefer testing both adapter modes when touching event parsing, token flow, or reply helpers.

## Commit & Pull Request Guidelines
Git history is minimal (`Initial open-source release`), so use short imperative subjects such as `Add webhook signature validation`. Keep commits scoped to one change. PRs should explain the user-visible effect, note any config/schema updates, link related issues, and include screenshots or log snippets when changing message rendering, templates, or webhook behavior.

## Security & Configuration Tips
Never commit real `appid`, `secret`, webhook UUIDs, or private backend URLs. Keep secrets in AstrBot configuration, and document new config keys in `metadata.yaml` when they are exposed to users.
