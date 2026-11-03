# Security policy

Privileged operations are denied unless the runtime verifies an action-bound approval through its configured host authority. The canonical production approval path is the GitHub pull-request verifier documented in `DEPLOY.md`.

Do not report the approval authority as connected until a read-only fine-grained token is stored in the runtime host secret manager, the exact target repository is included in `UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES`, the trusted reviewer and protected base branch are configured, the approval ledger is on persistent storage, and live positive, stale-review, revocation, wrong-digest and replay tests have passed.

Never commit credentials, token values, state databases, or approval ledger contents. Report security issues privately to the repository owner.


## Release review and deployment gate

- Every production code change must be reviewed on a pull request against the exact head SHA.
- The repository owner is listed in CODEOWNERS, but CODEOWNERS only has effect when repository rules require code-owner review.
- Require the runtime CI workflow before merging. Do not deploy this branch until an independent review has no unresolved critical/high findings, the protected-branch ruleset is verified, and a live approval/revocation/replay test passes against the actual host secret manager.
