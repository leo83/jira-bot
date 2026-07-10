# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Telegram bot that creates and looks up Jira issues. Users register their **personal** Jira API token (`/register`, private chat only); the bot performs every Jira action as that user. Primary commands: `/task` `/bug` `/story` (create), `/desc` (view), `/search` (full-text find), `/link` `/unlink` (associate a Grafana message ref with a Jira issue). Target Jira is **Server/DC** (Bearer PAT auth), not Cloud.

## Commands

```bash
uv sync --group dev            # install deps (incl. dev: pytest, black, isort, flake8, mypy)
uv run pytest -q               # run all tests
uv run pytest tests/test_jira_service.py::test_search_is_case_insensitive   # single test
uv run pytest -k assignee      # tests matching a keyword
uv run python main.py          # run the bot locally (needs a populated .env)
just local                     # kill any running instance + run locally
uv run black app/ tests/       # format (see note below)
```

`just docker-build` builds+pushes a prod image; `just helm-deploy` upgrades the `production` release. See **Deploy** for the important gap between them.

## Configuration

All config is env vars read at import time in `app/config.py` (`Config`) and `app/users.py` (`UserConfig`), loaded from `.env` via `python-dotenv`. `Config.validate()` runs at startup and requires `TELEGRAM_BOT_TOKEN`, `CH_USER`, `CH_PASSWORD`, `TOKEN_ENCRYPTION_KEY` (a Fernet key). `ALLOWED_USERS` is an allowlist of usernames/IDs — **empty means everyone is allowed** (fail-open). `OPENAI_*` are optional (LLM assignee/epic guessing; absent → fuzzy-only). `JIRA_USERNAME`/`JIRA_API_TOKEN` are legacy/unused (tokens are now per-user).

## Architecture

**Entry:** `main.py` → `TelegramBot.run()` (`app/telegram_bot.py`). `run()` uses an explicit async PTB lifecycle (initialize/start_polling/stop) with a cold-start retry loop and signal-based shutdown, tuned for running behind a proxy in Kubernetes.

**Per-user token flow (central pattern):** there is no shared Jira client. On each command, `_get_user_jira_service(telegram_id)` reads the user's Fernet-encrypted token from ClickHouse (`DatabaseService`), decrypts it (`CryptoService`), and builds a fresh `JiraService.with_token(...)`. From that per-user `JiraService`, the handler constructs per-request `ComponentService`, `SprintService`, `AssigneeService`, `EpicService`. Nothing is cached across commands except within a single service instance.

**Command handlers** live in the `TelegramBot` monolith. Every handler is registered wrapped in `_with_retry(...)`, which retries transient Telegram `NetworkError` with exponential backoff and, after exhausting retries, calls `os._exit(1)` so Kubernetes restarts the pod.

**Parameter parsing — the fragile core:** `_parse_task_parameters` extracts `type:`, `component:`, `sprint:`, `desc:`/`description:`, `link:`, `project:`, `assignee:`/`who:`, `epic:` from free-form text via one regex, in any order. Two things must stay in sync when adding a parameter:
- the keyword list appears **twice** in `param_pattern` (the capture alternation *and* the lookahead) — update both or summary extraction breaks;
- it returns a **positional tuple** that is unpacked identically at three duplicated create paths — `task_command`, `_process_bug_or_story` (/bug, /story), and `_process_task` (photo captions). Adding a field means editing the tuple, all three unpack sites, and every `should_stop` early-return in the parser. `tests/test_parse_task_parameters.py` maps the tuple to names and asserts its arity to catch mismatches.

**"Guessing" services** all follow the same shape: transliterate the query (Russian→Latin via `transliterate`) and fuzzy-match (`difflib`) against a candidate pool, returning `(value, message)` where a non-empty `message` means "stop and show the user" (not found / ambiguous). Each is independent (some duplication is intentional and matches the existing style):
- `IssueTypeService`, `ComponentService` — static/Jira-fetched lists.
- `SprintService` — Jira boards/sprints; handles `active`.
- `AssigneeService`, `EpicService` — fetch the pool from Jira (assignable users / `issuetype = Epic`), fuzzy-match, and fall back to `LLMService` only when fuzzy finds nothing. Ambiguity (several close matches) is detected from the candidate set and surfaced to the user rather than resolved by the LLM.

`LLMService` (`app/llm_service.py`) is a thin OpenAI-compatible client (no LangChain), 5s timeout, `verify=False` for the self-signed internal endpoint. It degrades to `None` on any error/missing config so callers fall back to fuzzy. It is **not** wired into the Helm deployment env, so the LLM booster is inactive in prod unless `OPENAI_*` is added there.

**JiraService (`app/jira_service.py`)** is the only Jira-facing module. `create_story` fails if the component doesn't exist, but sprint/assignee/epic are best-effort **post-create** (via `add_issues_to_sprint` / `assign_issue` / `add_issues_to_epic`) so a failure there never aborts issue creation. `search_issues` builds JQL that is case-insensitive (words lowercased), prefix-partial (`word*`), and AND-across-words (all words required, any order) — see `_build_text_clause`.

**Storage (ClickHouse via `DatabaseService`):** two concerns — `jira_issues` (message_ref ↔ jira_key links for `/link`) and `user_tokens` (a `ReplacingMergeTree`; reads use `FINAL`, deletes use `ALTER TABLE ... DELETE` mutations). `_ensure_connection()` reconnects on a dead client before each query. DDL and a migration live in `db/`.

## Gotchas

- **Blocking I/O in async handlers.** All Jira and ClickHouse calls are synchronous and are `await`ed only for Telegram replies. PTB processes updates sequentially, so a slow Jira/LLM call blocks the whole bot. Do **not** naively wrap these in `asyncio.to_thread` — `clickhouse_driver.Client` is not thread-safe.
- **Tests can't import services normally.** `DatabaseService`, `JiraService`, `TelegramBot` all connect/instantiate clients in `__init__`. Tests either patch the client class (`patch("app.jira_service.JIRA")`, `patch("app.database_service.Client")`) or build the object with `object.__new__(TelegramBot)` and set attributes manually. `pytest-asyncio` runs in `asyncio_mode = auto` (async tests need no marker).
- **Formatting is not enforced repo-wide.** The pre-existing `app/*.py` files are not black-clean, so do **not** run black across them (it churns unrelated code). Format only new/edited files.

## Deploy

Production runs in Kubernetes namespace `production` via the Helm chart in `helm/`.

1. `just docker-build` computes a date tag (`scripts/next_rc_version.py --prod`, e.g. `20260710.1`) by reading the registry, builds `linux/amd64`, and pushes.
2. **The two `just` recipes are decoupled:** `helm-deploy` reads `helm/jira-bot/values-production.yaml`, whose `image.tag` is **hardcoded**. After building, bump that tag to the newly-pushed one or `helm-deploy` re-deploys the old image.
3. `just helm-deploy` → `helm upgrade --install`. Verify with `kubectl rollout status deployment/jira-bot -n production` and check logs for `Bot is running`.

`values-production.yaml` is **gitignored** (it holds real secrets and the tag). The Helm deployment template passes only a fixed set of env vars — adding a new `Config` var that must reach prod means editing that template too.
