"""CrediDesk CRM client — reads JWT from env, calls customer endpoints.

Captured 26 May 2026 via Proxyman against Bruno Sousa's account
(DS Crédito Ramada – Jardim da Amoreira, agency 839).

Auth note: /userlogin returns an encrypted `cdko` blob that the Nuxt SPA
decrypts client-side to mint the JWT. Rather than reversing the JS,
`auth.mint_jwt()` drives a headless Chromium through the login flow and
captures the JWT from the first outgoing Bearer request. If DS_CRM_JWT is
missing or expired, the client auto-mints a fresh one and persists it.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Iterator

import requests

from .auth import mint_jwt, persist_jwt

API_BASE = "https://appapi.credidesk.com/api/v1"
LOGIN_URL = "https://authapi.credidesk.com/api/v1/account/app/userlogin"
ORIGIN = "https://crm.dsicredito.pt"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def _jwt_remaining_seconds(jwt: str) -> int:
    """Seconds until exp; negative if expired; raises on malformed JWT."""
    payload_b64 = jwt.split(".")[1]
    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    return int(payload["exp"]) - int(time.time())


def _env_path() -> Path:
    return Path(__file__).resolve().parents[2] / ".env"


class CredidekClient:
    # Refresh proactively when fewer than this many seconds remain — avoids
    # mid-ingest 401s during long paginations.
    REFRESH_MARGIN_S = 300

    def __init__(
        self,
        jwt: str | None = None,
        *,
        auto_refresh: bool = True,
        email: str | None = None,
        password: str | None = None,
    ):
        # Per-account mode: when explicit creds are given, this client logs in as
        # that CrediDesk user and keeps its JWT entirely in memory — it ignores
        # the shared DS_CRM_JWT (Bruno's) and never writes back to .env. This is
        # what lets the ingest loop pull each platform user's own CRM scope.
        self._email = email
        self._password = password
        self.jwt = jwt or ("" if email else os.environ.get("DS_CRM_JWT")) or ""
        self.auto_refresh = auto_refresh
        if not self.jwt or self._needs_refresh():
            if not auto_refresh:
                raise RuntimeError("DS_CRM_JWT missing/expired and auto_refresh=False")
            self._refresh_jwt()
        self.session = requests.Session()
        # Bypass any system HTTPS_PROXY (e.g. Proxyman still listening on localhost:9090)
        # so we get the real credidesk LetsEncrypt cert, not Proxyman's CA.
        self.session.trust_env = False
        self._apply_jwt_headers()
        self._log_jwt_status()

    def _apply_jwt_headers(self):
        self.session.headers.update({
            "Authorization": f"Bearer {self.jwt}",
            "Origin": ORIGIN,
            "Referer": f"{ORIGIN}/",
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
        })

    def _needs_refresh(self) -> bool:
        try:
            return _jwt_remaining_seconds(self.jwt) < self.REFRESH_MARGIN_S
        except Exception:
            return True

    def _refresh_jwt(self):
        email = self._email or os.environ.get("DS_CRM_USERNAME")
        password = self._password or os.environ.get("DS_CRM_PASSWORD")
        if not email or not password:
            raise RuntimeError("DS_CRM_USERNAME/PASSWORD missing — cannot mint a fresh JWT")
        print(f"[crm] minting fresh JWT for {email}...")
        t0 = time.time()
        self.jwt = mint_jwt(email, password)
        # Only the shared (env) account persists its JWT to .env; a per-account
        # client keeps it in memory so it never clobbers Bruno's DS_CRM_JWT.
        if not self._email:
            persist_jwt(self.jwt, _env_path())
            print(f"[crm] minted JWT in {time.time()-t0:.1f}s and wrote to .env")
        else:
            print(f"[crm] minted in-memory JWT in {time.time()-t0:.1f}s for {email}")
        if hasattr(self, "session"):
            self._apply_jwt_headers()

    def _log_jwt_status(self):
        payload_b64 = self.jwt.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        remaining_min = (int(payload["exp"]) - int(time.time())) // 60
        print(f"[crm] JWT valid for {remaining_min} more minutes (user {payload['email']}, agency {payload['agencyId']})")

    def _request(self, method: str, path: str, **kwargs) -> dict:
        url = f"{API_BASE}{path}"
        r = self.session.request(method, url, timeout=30, **kwargs)
        if r.status_code == 401 and self.auto_refresh:
            print("[crm] 401 mid-flight — refreshing JWT and retrying once")
            self._refresh_jwt()
            r = self.session.request(method, url, timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        return self._request("POST", path, json=body)

    def _get(self, path: str) -> dict:
        return self._request("GET", path)

    def list_customers_page(self, page: int = 1, page_size: int = 50) -> dict:
        body = {
            "startDate": None, "endDate": None, "name": "", "taxNumber": None,
            "typeId": 0, "districtId": 0, "countyId": 0, "parishId": 0,
            "customerId": 0, "stateId": 0,
            "pageNumber": page, "pageNResults": page_size,
            "orderBy": "", "ordering": 1, "ongoingCreditProcess": False,
        }
        return self._post("/customers/list", body)

    def iter_customers(self, page_size: int = 50) -> Iterator[dict]:
        yield from self._paginate(
            self.list_customers_page, page_size=page_size, data_key="data",
        )

    def list_processos_page(self, page: int = 1, page_size: int = 50, *, archived: bool = True) -> dict:
        # Body mirrors the SPA's request (captured 22 Jul 2026 on pd/Loulé).
        # CRITICAL: filterAgencyId/filterCompanyId must be null, not 0 — with 0
        # the API silently narrows the list to the JWT user's own processos
        # (pd: 9 vs 744; bs: 197 vs 860). null = everything the account can see.
        body = {
            "startDate": None, "endDate": None, "stateId": 0, "typeId": 0,
            "customerId": 0, "reference": "", "nameCustomer": "",
            "managerId": 0, "documentsNotValidated": 0,
            "notificationsNotTreated": 0, "documentsNotUploaded": 0,
            "creditEntityId": 0, "creditEntityAgencyId": 0,
            "creditEntityAgencyContactId": 0, "archived": archived,
            "filterAgencyId": None, "filterCompanyId": None,
            "isCreditCard": False, "taxNumber": 0, "labelId": 0,
            "dateType": 0, "nDays": 0,
            "pageNumber": page, "pageNResults": page_size,
            "orderBy": "", "ordering": 1,
            "search": {
                "leadOriginId": 0, "leadCampaignId": 0,
                "kanbanStageId": 0, "kanbanId": 0, "noScheduledTasks": None,
            },
        }
        return self._post("/creditprocesses/list", body)

    def iter_processos(self, page_size: int = 50, *, archived: bool = True) -> Iterator[dict]:
        def fetch(page, ps):
            return self.list_processos_page(page=page, page_size=ps, archived=archived)
        yield from self._paginate(fetch, page_size=page_size, data_key="creditprocess")

    def list_leads_page(self, page: int = 1, page_size: int = 50, *, state_id: int = 0, archived: bool = False) -> dict:
        body = {
            "startDate": None, "endDate": None, "name": "",
            "creditTypeId": 0, "originId": 0, "managerId": 0,
            "stateId": state_id, "ongoingCreditProcess": False,
            "pageNumber": page, "pageNResults": str(page_size),
            "orderBy": "", "ordering": 2,
            "dateType": 0, "labelId": 0, "archived": archived,
            "reference": "",
            "search": {
                "telephone": None, "leadOriginId": 0, "leadCampaignId": 0,
                "subStateId": 0, "noScheduledTasks": None,
            },
            "email": "",
        }
        return self._post("/customerspotential/leads/list", body)

    def iter_leads(self, page_size: int = 50, *, state_id: int = 0, archived: bool = False) -> Iterator[dict]:
        def fetch(page, ps):
            return self.list_leads_page(page=page, page_size=ps, state_id=state_id, archived=archived)
        yield from self._paginate(fetch, page_size=page_size, data_key="customer")

    def _paginate(self, fetch, *, page_size: int, data_key: str) -> Iterator[dict]:
        page = 1
        total_pages = None
        while True:
            res = fetch(page, page_size)
            if res.get("success") != 1:
                print(f"[crm] page {page}: success != 1, stopping. message={res.get('message')}")
                break
            data = res.get(data_key) or []
            if not data:
                break
            for row in data:
                yield row
            total_pages = res.get("totalpages") or total_pages
            total_records = res.get("totalrecords")
            print(f"[crm] page {page}: {len(data)} rows (total {total_records} across {total_pages} pages)")
            if total_pages and page >= total_pages:
                break
            page += 1
            time.sleep(0.5)  # be polite to Bruno's CRM


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    c = CredidekClient()
    first_page = c.list_customers_page(page=1, page_size=5)
    print(json.dumps(first_page, indent=2, ensure_ascii=False)[:3000])
