from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import base64
import hashlib
import json
import os
import re
import sqlite3
import time


class ApprovalVerifier(Protocol):
    """Host trust boundary; implementations must authenticate the approver and approval record."""

    def verify(self, approval: Any, permission: str, action_digest: str) -> bool:
        """Return true only for a trusted, unexpired approval bound to this action and permission."""
        ...


class ApprovalLedger(Protocol):
    """Durable one-use ledger for verified approval consumption."""

    def consume_once(self, approval_id: str, action_digest: str) -> bool:
        ...


def canonical_action_digest(action_details: Mapping[str, Any]) -> str:
    """Hash exact operation metadata without persisting its private payload values."""
    if not isinstance(action_details, Mapping):
        raise TypeError('Approval action_details must be a mapping.')
    encoded = json.dumps(dict(action_details), sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class GitHubPullRequestApprovalVerifier:
    """Verify one-time privileged approvals through authenticated GitHub PR reviews.

    The approval request is an immutable JSON file in the PR head commit. The
    review must be an APPROVED review on that exact commit by a configured
    trusted GitHub administrator. Pull requests must remain open and target the
    configured base branch. Successful approvals are atomically consumed in a
    local SQLite ledger to prevent replay.
    """

    API_BASE = 'https://api.github.com'
    SCHEMA = 'uneXpected.approval-request/v1'
    APPROVAL_ID = re.compile(r'^github-pr:(\d+):([A-Za-z0-9][A-Za-z0-9._-]{0,63})$')
    PROPOSAL_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
    DIGEST = re.compile(r'^[0-9a-f]{64}$')
    LOGIN = re.compile(r'^[A-Za-z0-9-]{1,39}$')
    MAX_RESPONSE_BYTES = 1_000_000

    def __init__(self, *, repository: str, token: str,
                 trusted_reviewers: tuple[str, ...] | list[str],
                 base_branch: str = 'main', max_age_seconds: int = 3600,
                 ledger_path: str | Path = 'state/approval-ledger.sqlite3',
                 timeout_seconds: float = 8.0,
                 transport: Callable[[str], Any] | None = None,
                 ledger: ApprovalLedger | None = None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository or ''):
            raise ValueError('A fixed GitHub owner/repository is required.')
        reviewers = tuple(dict.fromkeys(str(x).strip().lower() for x in trusted_reviewers if str(x).strip()))
        if any(not self.LOGIN.fullmatch(x) for x in reviewers):
            raise ValueError('Trusted GitHub reviewer names are malformed.')
        if not re.fullmatch(r'[A-Za-z0-9._/-]{1,100}', base_branch or '') or '..' in base_branch:
            raise ValueError('Base branch is malformed.')
        if not isinstance(max_age_seconds, int) or not 60 <= max_age_seconds <= 604800:
            raise ValueError('Approval max age must be between 60 seconds and 7 days.')
        if not isinstance(timeout_seconds, (int, float)) or not 1 <= timeout_seconds <= 20:
            raise ValueError('GitHub request timeout must be between 1 and 20 seconds.')
        self.repository = repository
        self.owner, self.repo = repository.split('/', 1)
        self.token = str(token or '').strip()
        self.trusted_reviewers = frozenset(reviewers)
        self.base_branch = base_branch
        self.max_age_seconds = max_age_seconds
        self.ledger_path = Path(ledger_path)
        self.timeout_seconds = float(timeout_seconds)
        self.transport = transport
        self.ledger = ledger

    def _get_json(self, path: str) -> Any:
        if self.transport is not None:
            return self.transport(path)
        if not self.token:
            raise PermissionError('GitHub approval token is not configured.')
        if not path.startswith(f'/repos/{self.owner}/{self.repo}/') or '\n' in path or '\r' in path:
            raise ValueError('GitHub API path is outside the configured repository.')
        request = Request(
            self.API_BASE + path,
            headers={
                'Accept': 'application/vnd.github+json',
                'Authorization': f'Bearer {self.token}',
                'X-GitHub-Api-Version': '2026-03-10',
                'User-Agent': 'uneXpected-approval-verifier/7.3',
            },
            method='GET',
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            # Do not propagate response bodies or token-bearing request metadata.
            raise PermissionError('GitHub approval verification request failed.') from exc
        if len(raw) > self.MAX_RESPONSE_BYTES:
            raise PermissionError('GitHub approval response exceeded the configured limit.')
        try:
            return json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PermissionError('GitHub approval response was not valid JSON.') from exc

    @staticmethod
    def _parse_time(value: Any) -> float:
        if not isinstance(value, str) or not value:
            raise ValueError('Timestamp missing.')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError('Timestamp must include a timezone.')
        return parsed.astimezone(timezone.utc).timestamp()

    def _read_request_document(self, proposal_id: str, head_sha: str) -> dict[str, Any]:
        path = (f'/repos/{self.owner}/{self.repo}/contents/approvals/requests/'
                f'{proposal_id}.json?ref={head_sha}')
        result = self._get_json(path)
        if not isinstance(result, dict) or result.get('encoding') != 'base64':
            raise ValueError('Approval request file missing or not base64 encoded.')
        encoded = result.get('content')
        if not isinstance(encoded, str):
            raise ValueError('Approval request file content missing.')
        compact = ''.join(encoded.split())
        decoded = base64.b64decode(compact, validate=True)
        if len(decoded) > 16_384:
            raise ValueError('Approval request file too large.')
        data = json.loads(decoded.decode('utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Approval request file must contain a JSON object.')
        return data

    def _consume_once(self, approval_id: str, action_digest: str) -> bool:
        if self.ledger is not None:
            return self.ledger.consume_once(approval_id, action_digest)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.ledger_path, timeout=5.0, isolation_level=None) as connection:
            connection.execute('PRAGMA busy_timeout=5000')
            connection.execute('''CREATE TABLE IF NOT EXISTS consumed_approvals (
                approval_id TEXT PRIMARY KEY,
                action_digest TEXT NOT NULL,
                consumed_at REAL NOT NULL
            )''')
            connection.execute('BEGIN IMMEDIATE')
            try:
                connection.execute(
                    'INSERT INTO consumed_approvals(approval_id, action_digest, consumed_at) VALUES (?, ?, ?)',
                    (approval_id, action_digest, time.time()),
                )
                connection.execute('COMMIT')
                return True
            except sqlite3.IntegrityError:
                connection.execute('ROLLBACK')
                return False
            except Exception:
                connection.execute('ROLLBACK')
                raise

    def verify(self, approval: Any, permission: str, action_digest: str) -> bool:
        try:
            if (not self.token or not self.trusted_reviewers
                    or approval is None
                    or not isinstance(action_digest, str) or not self.DIGEST.fullmatch(action_digest)
                    or not isinstance(permission, str) or not permission):
                return False
            approval_id = getattr(approval, 'approval_id', '')
            match = self.APPROVAL_ID.fullmatch(approval_id) if isinstance(approval_id, str) else None
            if not match:
                return False
            pr_number, proposal_id = int(match.group(1)), match.group(2)
            if pr_number <= 0 or not self.PROPOSAL_ID.fullmatch(proposal_id):
                return False
            claimed_reviewer = str(getattr(approval, 'approver', '')).lower()
            approved_permissions = getattr(approval, 'approved_permissions', frozenset())
            if (claimed_reviewer not in self.trusted_reviewers
                    or permission not in approved_permissions
                    or getattr(approval, 'action_digest', '') != action_digest):
                return False

            prefix = f'/repos/{self.owner}/{self.repo}'
            pull = self._get_json(f'{prefix}/pulls/{pr_number}')
            if not isinstance(pull, dict) or pull.get('state') != 'open' or pull.get('draft') is True:
                return False
            base = pull.get('base') or {}
            head = pull.get('head') or {}
            author = (pull.get('user') or {}).get('login', '').lower()
            head_ref = head.get('ref', '')
            head_repo = (head.get('repo') or {}).get('full_name', '')
            base_repo = (base.get('repo') or {}).get('full_name', '')
            head_sha = head.get('sha', '')
            if (base.get('ref') != self.base_branch or base_repo.lower() != self.repository.lower()
                    or head_repo.lower() != self.repository.lower() or not re.fullmatch(r'[0-9a-f]{40}', head_sha)
                    or head_ref != f'approval-requests/{proposal_id}'
                    or author != 'github-actions[bot]' or author in self.trusted_reviewers):
                return False

            request_doc = self._read_request_document(proposal_id, head_sha)
            if (request_doc.get('schema') != self.SCHEMA
                    or request_doc.get('proposal_id') != proposal_id
                    or str(request_doc.get('repository', '')).lower() != self.repository.lower()
                    or request_doc.get('permission') != permission
                    or not isinstance(request_doc.get('action_details'), dict)
                    or permission not in request_doc['action_details'].get('required_permissions', [])
                    or canonical_action_digest(request_doc['action_details']) != action_digest
                    or request_doc.get('action_digest') != action_digest):
                return False
            requested_by = str(request_doc.get('requested_by', '')).strip().lower()
            # Requests are issued only by the configured repository owner. The
            # approving admin must be a different identity (separation of duties).
            if requested_by != self.owner.lower() or requested_by == claimed_reviewer:
                return False
            created_at = self._parse_time(request_doc.get('created_at'))
            pull_created_at = self._parse_time(pull.get('created_at'))
            now = time.time()
            if (created_at > now + 60 or now - created_at > self.max_age_seconds
                    or created_at > pull_created_at + 60):
                return False

            reviews = self._get_json(f'{prefix}/pulls/{pr_number}/reviews?per_page=100&page=1')
            if not isinstance(reviews, list) or len(reviews) >= 100:
                # A full page may hide a later revocation or changes-requested review.
                return False
            reviewer_reviews = []
            for review in reviews:
                login = ((review.get('user') or {}).get('login') or '').lower()
                if login in self.trusted_reviewers:
                    submitted_at = self._parse_time(review.get('submitted_at'))
                    reviewer_reviews.append((submitted_at, login, review))
            if not reviewer_reviews:
                return False
            reviewer_reviews.sort(key=lambda row: row[0])
            latest_any = reviewer_reviews[-1]
            latest_for_claimed = [row for row in reviewer_reviews if row[1] == claimed_reviewer]
            if not latest_for_claimed:
                return False
            latest = latest_for_claimed[-1]
            if (latest[2].get('state') != 'APPROVED'
                    or latest[2].get('commit_id') != head_sha
                    or latest[0] < created_at
                    or latest[0] < pull_created_at
                    or latest_any[1] != claimed_reviewer
                    or latest_any[2].get('state') != 'APPROVED'
                    or now - latest[0] > self.max_age_seconds):
                return False

            permission_data = self._get_json(
                f'{prefix}/collaborators/{claimed_reviewer}/permission')
            if not isinstance(permission_data, dict) or permission_data.get('permission') != 'admin':
                return False

            # A valid GitHub approval is single-use. The insert is atomic across workers.
            return self._consume_once(approval_id, action_digest)
        except Exception:
            # Any malformed response, API outage, parse error, or ledger failure denies access.
            return False


def approval_verifier_from_env(state_dir: str | Path | None = None) -> GitHubPullRequestApprovalVerifier | None:
    """Build the production verifier only when all required trust settings exist."""
    token = os.getenv('UNEXPECTED_GITHUB_APPROVAL_TOKEN', '').strip()
    repository = os.getenv('UNEXPECTED_GITHUB_APPROVAL_REPOSITORY', '').strip()
    allowed_repositories = tuple(x.strip().lower() for x in os.getenv('UNEXPECTED_GITHUB_APPROVAL_ALLOWED_REPOSITORIES', '').split(',') if x.strip())
    reviewers = tuple(x.strip() for x in os.getenv('UNEXPECTED_GITHUB_APPROVAL_TRUSTED_REVIEWERS', '').split(',') if x.strip())
    if (not token or not repository or not reviewers or not allowed_repositories
            or repository.lower() not in set(allowed_repositories)):
        return None
    try:
        ledger_backend = os.getenv('UNEXPECTED_APPROVAL_LEDGER_BACKEND', os.getenv('UNEXPECTED_STORAGE_BACKEND', 'sqlite')).strip().lower()
        ledger = None
        if ledger_backend == 'postgres':
            database_url = os.getenv('DATABASE_URL', '').strip()
            if not database_url:
                return None
            from .postgres_approval_ledger import PostgresApprovalLedger
            ledger = PostgresApprovalLedger(database_url)
        elif ledger_backend != 'sqlite':
            return None
        max_age = int(os.getenv('UNEXPECTED_GITHUB_APPROVAL_MAX_AGE_SECONDS', '3600'))
        timeout = float(os.getenv('UNEXPECTED_GITHUB_APPROVAL_TIMEOUT_SECONDS', '8'))
        ledger_override = os.getenv('UNEXPECTED_APPROVAL_LEDGER_PATH', '').strip()
        ledger_path = ledger_override or str(Path(state_dir or 'state') / 'approval-ledger.sqlite3')
        return GitHubPullRequestApprovalVerifier(
            repository=repository,
            token=token,
            trusted_reviewers=reviewers,
            base_branch=os.getenv('UNEXPECTED_GITHUB_APPROVAL_BASE_BRANCH', 'main').strip(),
            max_age_seconds=max_age,
            timeout_seconds=timeout,
            ledger_path=ledger_path,
            ledger=ledger,
        )
    except (TypeError, ValueError):
        return None
