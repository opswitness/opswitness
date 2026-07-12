"""Thin Paperclip API client — only the surfaces the projector needs (ADR-0001 v3).

Response shapes are tolerated loosely (list vs {items:[...]}) because Paperclip publishes
no compatibility promise; the projector treats every remote read as reconciliation input,
never as authority.
"""

from typing import Any

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
        self, issue_id: str, body: str, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        return self._req(
            "POST",
            f"/api/issues/{issue_id}/comments",
            json={"body": body, "metadata": metadata},
        )
