"""Thin Paperclip API client — only the surfaces the projector needs (ADR-0001 v3).

Response shapes are tolerated loosely (list vs {items:[...]}) because Paperclip publishes
no compatibility promise; the projector treats every remote read as reconciliation input,
never as authority.
"""

from typing import Any
from uuid import UUID

import httpx


class PaperclipError(Exception):
    pass


def _items(data: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return data[key]
    return []


class PaperclipClient:
    def __init__(
        self,
        api_base: str,
        api_key: str,
        company_id: str,
        *,
        timeout: float = 15.0,
        issue_status: str = "todo",
    ) -> None:
        self.company_id = company_id
        self.issue_status = issue_status
        self._client = httpx.Client(
            base_url=api_base,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def _req(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            resp = self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise PaperclipError(f"{method} {url}: {exc}") from exc
        if resp.status_code >= 400:
            raise PaperclipError(f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]}")
        if resp.text:
            return resp.json()
        return None

    def list_issues(self) -> list[dict[str, Any]]:
        data = self._req("GET", f"/api/companies/{self.company_id}/issues")
        return _items(data, "issues", "items", "data")

    def create_issue(self, title: str, description: str) -> dict[str, Any]:
        return self._req(
            "POST",
            f"/api/companies/{self.company_id}/issues",
            json={"title": title, "description": description, "status": self.issue_status},
        )

    def list_comments(self, issue_id: str) -> list[dict[str, Any]]:
        data = self._req("GET", f"/api/issues/{issue_id}/comments")
        return _items(data, "comments", "items", "data")

    def post_comment(
        self, issue_id: str, body: str, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"body": body}
        if metadata is not None:
            payload["metadata"] = metadata
        return self._req(
            "POST",
            f"/api/issues/{issue_id}/comments",
            json=payload,
        )

    def list_approvals(self, status: str | None = None) -> list[dict[str, Any]]:
        suffix = f"?status={status}" if status else ""
        data = self._req(
            "GET", f"/api/companies/{self.company_id}/approvals{suffix}"
        )
        return _items(data, "approvals", "items", "data")

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        data = self._req("GET", f"/api/approvals/{approval_id}")
        if not isinstance(data, dict):
            raise PaperclipError(f"approval {approval_id}: expected an object")
        return data

    def create_board_approval(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._req(
            "POST",
            f"/api/companies/{self.company_id}/approvals",
            json={"type": "request_board_approval", "payload": payload},
        )
        if not isinstance(data, dict):
            raise PaperclipError("create approval: expected an object")
        return data

    def resolve_approval(
        self,
        approval_id: str,
        decision: str,
        decision_note: str | None = None,
    ) -> dict[str, Any]:
        try:
            UUID(approval_id)
        except ValueError as exc:
            raise PaperclipError("approval id is invalid") from exc
        if decision not in {"approve", "reject"}:
            raise PaperclipError("approval decision is invalid")
        payload = {"decisionNote": decision_note or None}
        data = self._req("POST", f"/api/approvals/{approval_id}/{decision}", json=payload)
        if not isinstance(data, dict):
            raise PaperclipError("resolve approval: expected an object")
        return data

    def list_work_products(self, issue_id: str) -> list[dict[str, Any]]:
        data = self._req("GET", f"/api/issues/{issue_id}/work-products")
        return _items(data, "workProducts", "work_products", "items", "data")

    def create_work_product(
        self, issue_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._req("POST", f"/api/issues/{issue_id}/work-products", json=payload)
        if not isinstance(data, dict):
            raise PaperclipError("create work product: expected an object")
        return data
