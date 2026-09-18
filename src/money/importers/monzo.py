"""Monzo API integration.

Docs: https://docs.monzo.com/. Monzo's API is explicitly built for
personal-use tools like this one: an OAuth client you register yourself,
authorizing only your own account (Monzo also requires you to approve API
access inside the Monzo app itself after login, as an extra fraud check).

This module never runs itself against real credentials from inside a Claude
Code tool call -- `money.cli monzo-auth` / `money.cli import-monzo` are
meant to be run by you, in your own terminal. See README.md.
"""

from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from sqlite3 import Connection
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from money.categorize import Rule, categorize
from money.db import get_or_create_account, last_imported_date, record_balance, upsert_transaction

AUTH_URL = "https://auth.monzo.com/"
TOKEN_URL = "https://api.monzo.com/oauth2/token"
API_BASE = "https://api.monzo.com"

DEFAULT_REDIRECT_URI = "http://localhost:6600/monzo/callback"


class _CallbackHandler(BaseHTTPRequestHandler):
    """Captures the ?code=... redirect from Monzo's auth page."""

    captured_code: str | None = None

    def do_GET(self):  # noqa: N802 (http.server naming convention)
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        _CallbackHandler.captured_code = code
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        msg = b"Authorized. You can close this tab and return to your terminal."
        if not code:
            msg = b"No authorization code received -- check your terminal."
        self.wfile.write(msg)

    def log_message(self, format, *args):  # silence default request logging
        pass


def _wait_for_callback(port: int, timeout: int = 300) -> str:
    server = HTTPServer(("localhost", port), _CallbackHandler)
    server.timeout = timeout
    _CallbackHandler.captured_code = None
    deadline = time.monotonic() + timeout
    while _CallbackHandler.captured_code is None and time.monotonic() < deadline:
        server.handle_request()
    server.server_close()
    if not _CallbackHandler.captured_code:
        raise TimeoutError("Timed out waiting for the Monzo OAuth redirect.")
    return _CallbackHandler.captured_code


def authorize(
    client_id: str,
    client_secret: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> dict:
    """Interactive OAuth flow: opens a browser, waits for the redirect on a
    local port, exchanges the code for tokens. Run this yourself, once, from
    your own terminal -- it opens a real browser window against your real
    Monzo login.
    """
    state = str(int(time.time()))
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"Opening browser to authorize with Monzo:\n{url}\n")
    webbrowser.open(url)

    port = urlparse(redirect_uri).port
    code = _wait_for_callback(port)

    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=30,
    )
    resp.raise_for_status()
    tokens = resp.json()
    print(
        "Authorized. Now open the Monzo app on your phone and approve API "
        "access when prompted, before running import-monzo."
    )
    return _normalize_tokens(tokens)


def refresh_tokens(client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return _normalize_tokens(resp.json())


def _normalize_tokens(tokens: dict) -> dict:
    return {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": time.time() + tokens.get("expires_in", 0),
    }


def parse_account_name_overrides(raw: str) -> dict[str, str]:
    """Parses MONZO_ACCOUNT_NAME_OVERRIDES from .env: "id1:Name One,id2:Name
    Two" -> {"id1": "Name One", "id2": "Name Two"}. Empty/missing input
    returns {}, so this is a no-op until you opt in.
    """
    overrides = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        account_id, name = pair.split(":", 1)
        account_id, name = account_id.strip(), name.strip()
        if account_id and name:
            overrides[account_id] = name
    return overrides


def load_token_store(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def save_token_store(path: Path, tokens: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tokens, indent=2))


@dataclass
class MonzoClient:
    access_token: str
    session: requests.Session

    def _get(self, path: str, params: dict | None = None) -> dict:
        resp = self.session.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def list_accounts(self) -> list[dict]:
        data = self._get("/accounts")
        # Only open, real accounts (Monzo also returns closed/prepaid types).
        return [
            a for a in data.get("accounts", [])
            if not a.get("closed", False)
        ]

    def balance(self, account_id: str) -> dict:
        data = self._get("/balance", params={"account_id": account_id})
        return {
            "balance": data["balance"] / 100,
            "currency": data["currency"],
        }

    def list_transactions(self, account_id: str, since: str | None = None) -> list[dict]:
        params = {"account_id": account_id, "expand[]": "merchant"}
        if since:
            params["since"] = since
        data = self._get("/transactions", params=params)
        return data.get("transactions", [])


def normalize_transaction(txn: dict) -> dict:
    """Map a raw Monzo transaction into this app's common shape."""
    merchant = txn.get("merchant")
    merchant_name = merchant.get("name") if isinstance(merchant, dict) else None
    return {
        "date": txn["created"][:10],
        "amount": txn["amount"] / 100,
        "description": txn.get("description", ""),
        "merchant": merchant_name,
        "external_id": txn["id"],
    }


def ensure_fresh_client(
    client_id: str,
    client_secret: str,
    token_path: Path,
    session: requests.Session | None = None,
) -> MonzoClient:
    """Load tokens from disk, refreshing them (and persisting the refreshed
    pair) if the access token is expired or close to it.
    """
    tokens = load_token_store(token_path)
    if not tokens:
        raise RuntimeError(
            "No Monzo tokens found. Run `python -m money.cli monzo-auth` first."
        )
    if tokens["expires_at"] - time.time() < 60:
        tokens = refresh_tokens(client_id, client_secret, tokens["refresh_token"])
        save_token_store(token_path, tokens)
    return MonzoClient(access_token=tokens["access_token"], session=session or requests.Session())


def run_import(
    conn: Connection,
    client_id: str,
    client_secret: str,
    token_path: Path,
    rules: list[Rule],
    account_name_overrides: dict[str, str] | None = None,
) -> dict:
    """Fetch new transactions + current balance for every open Monzo
    account, upsert into the DB. Returns row counts only (no financial
    data), suitable for printing/summarizing.

    `account_name_overrides` maps a Monzo account id -> a friendly display
    name, taking priority over Monzo's own `description` field. Needed
    because a shared/joint account can come back from the API with no
    description at all, in which case the fallback is the account's raw
    id -- not just ugly, but a real problem, since get_or_create_account
    matches accounts by (institution, name): without an override, an
    empty description means every import recomputes that same raw-id
    fallback name, so a manually-renamed account would otherwise get a
    fresh duplicate row next time rather than keeping the rename.
    """
    client = ensure_fresh_client(client_id, client_secret, token_path)
    accounts = client.list_accounts()
    overrides = account_name_overrides or {}

    summary = {"accounts": []}
    for acc in accounts:
        account_name = overrides.get(acc["id"]) or acc.get("description") or acc["id"]
        account_id = get_or_create_account(
            conn, institution="Monzo", account_type=acc.get("type", "current"), name=account_name
        )

        since = last_imported_date(conn, account_id, source="monzo")
        since_iso = f"{since}T00:00:00Z" if since else None
        raw_txns = client.list_transactions(acc["id"], since=since_iso)

        inserted = updated = 0
        for raw in raw_txns:
            if raw.get("decline_reason"):
                continue  # skip declined transactions, they didn't happen
            norm = normalize_transaction(raw)
            category = categorize(norm["description"], norm["merchant"], rules)
            was_inserted = upsert_transaction(
                conn,
                account_id=account_id,
                date=norm["date"],
                amount=norm["amount"],
                description=norm["description"],
                merchant=norm["merchant"],
                category=category,
                source="monzo",
                external_id=norm["external_id"],
            )
            inserted += was_inserted
            updated += not was_inserted

        bal = client.balance(acc["id"])
        record_balance(conn, account_id, time.strftime("%Y-%m-%d"), bal["balance"])

        summary["accounts"].append(
            {"name": account_name, "inserted": inserted, "updated": updated}
        )

    conn.commit()
    return summary
