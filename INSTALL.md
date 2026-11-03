# Install uneXpected v7.3.1 (local scaffold)

## Requirements
- Python 3.10+ (standard library only); no upstream app dependencies are installed.
- A writable local state directory.
- Optional: an OpenAI-compatible endpoint configured via environment variables. Do not put credentials in chat, source files, `.env.example`, or logs.

## Local setup
1. Extract the ZIP to a dedicated directory; keep `/uneXpected/` legacy files unchanged.
2. Create a private environment configuration based on `.env.example` if using a real provider. The default is `UNEXPECTED_PROVIDER=mock`.
3. From the package root run `python -m unexpected_runtime.cli status`, `python -m unexpected_runtime.cli list`, then `python -m unexpected_runtime.cli run orchestrator --objective 'Plan a safe test task'` and `python -m unexpected_runtime.cli eval`.
4. Keep `uneXpected_v7.3.1_governed_runtime.zip` beside the extracted `uneXpected_v7/` directory (or set `UNEXPECTED_PACKAGE_ZIP` to its path), then run `python -m unittest discover -s tests -v`.
5. Review `TEST_RESULTS.md`, `CAPABILITY_MATRIX.md` and `THREAT_MODEL.md`.

## State
By default, SQLite state is stored under `./state/uneXpected.sqlite3`. Override with `UNEXPECTED_STATE_DIR`. Protect and back up this directory. Agent memory is namespaced by ID; shared knowledge is not returned until human-reviewed.

## Provider setup
Set `UNEXPECTED_PROVIDER=openai_compatible`, `UNEXPECTED_BASE_URL`, `UNEXPECTED_MODEL` and `UNEXPECTED_API_KEY` in the host environment. Run a harmless smoke test, check provider access/rate limits/costs and do not enable external tools until each integration has its own permission and acceptance test. The adapter is present but was not tested against a live provider in this build.

## Important boundary
This is a locally executable scaffold and mock-tested runtime. It is not a hosted always-on service, not installed into ChatGPT Projects, and not automatically connected to ChatGPT's browser/web/Gmail/Calendar or any third-party app.


## Host approval adapter contract
The package includes `GitHubPullRequestApprovalVerifier` and `approval_verifier_from_env()` as a production verifier implementation. It remains disabled until the host supplies a read-only GitHub token, an exact target repository included in `UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES`, trusted reviewer identities, and durable ledger storage. Until those settings are valid, privileged actions and protected self-improvement promotion/rollback remain denied. The verifier must bind identity, scope and exact action digest; a caller-supplied approval object is not sufficient. Durable privileged queue entries remain denied because no durable approval-reference revalidation adapter is included.
