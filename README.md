# Copy to a private environment file or export variables in the host shell.
# Do not commit real credentials and do not paste them into chat.
UNEXPECTED_STATE_DIR=./state
UNEXPECTED_STORAGE_BACKEND=sqlite
# Hosted mode must use a configured PostgreSQL URL and tested migrations.
# DATABASE_URL=

# Provider routes. Credentials stay in the host secret manager.
UNEXPECTED_DEFAULT_PROVIDER=mock
# OPENAI_API_KEY=
# OPENAI_MODEL=gpt-4.1-mini
# OPENAI_BASE_URL=https://api.openai.com/v1
# ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
# OPENROUTER_API_KEY=
# OPENROUTER_MODEL=openrouter/free
# OpenOx native Responses API route.
# OPENOX_API_KEY=
# OPENOX_BASE_URL=https://api.openoxai.com/v1
# OPENOX_MODEL=gpt-6-astra
UNEXPECTED_MAX_WORKERS=4
UNEXPECTED_MAX_RETRIES=1
UNEXPECTED_DEFAULT_TIMEOUT_SECONDS=30

# Private HTTP API. Generate a unique random token of at least 32 characters.
# UNEXPECTED_RUNTIME_API_TOKEN=

# GitHub approval verifier. A read-only token is stored only in the host secret manager.
UNEXPECTED_GITHUB_APPROVAL_TOKEN=
# Privileged actions remain denied until the host verifier and durable replay ledger pass tests.
UNEXPECTED_GITHUB_APPROVAL_REPOSITORY=soueilouay-creator/uneXxxx
UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES=
UNEXPECTED_GITHUB_APPROVAL_TRUSTED_REVIEWERS=
UNEXPECTED_GITHUB_APPROVAL_BASE_BRANCH=main
UNEXPECTED_GITHUB_APPROVAL_MAX_AGE_SECONDS=3600
UNEXPECTED_GITHUB_APPROVAL_TIMEOUT_SECONDS=8
UNEXPECTED_APPROVAL_LEDGER_PATH=./state/approval-ledger.sqlite3
# When storage is postgres, set UNEXPECTED_APPROVAL_LEDGER_BACKEND=postgres only after recovery tests.
# UNEXPECTED_APPROVAL_LEDGER_BACKEND=postgres


## Local-only AI Creator Studio (2026-11-09)

The supported local inference profile is selected with `UNEXPECTED_AI_MODE=local_only`. It registers only the loopback `local` provider route, rejects public endpoints and conflicting cloud-provider selections, disables proxy use and redirects, and does not fall back to mock or cloud. Configure `UNEXPECTED_LOCAL_BASE_URL=http://127.0.0.1:8080/v1` and an explicit `UNEXPECTED_LOCAL_MODEL` name for the local llama.cpp server.

The local model inventory is in `local_ai/model_registry.json`. All initial candidates remain `discovered`; no model weights are asserted installed or licensed. Inspect the computer's local runtime/model cache with `python -m unexpected_runtime.local_ai status --model-root ./models` and run `preflight` before production. These checks do not download or install anything. See `local_ai/README.md` for the local llama.cpp and ComfyUI offline launch procedures.

No cloud AI fallback, automatic model download or publishing is enabled by this profile.
