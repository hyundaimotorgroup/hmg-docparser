from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from requests.auth import HTTPBasicAuth

from core.services.confluence_upload.models import ConfluenceUploadOptions


class ConfluenceClient:
    def __init__(self, options: ConfluenceUploadOptions) -> None:
        parsed = urlparse(options.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("Confluence base_url must be an absolute HTTPS URL without query or fragment")
        self.base_url = options.base_url.rstrip("/")
        if not self.base_url.endswith("/wiki"):
            self.base_url += "/wiki"
        self.timeout = options.timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        if options.email:
            self.session.auth = HTTPBasicAuth(options.email, options.token)
        else:
            self.session.headers.update({"Authorization": f"Bearer {options.token}"})

    def get_space(self, space_id: str) -> dict[str, Any]:
        response = self.session.get(
            self._url(f"/rest/api/space/{space_id}"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_page_by_title(self, space_id: str, title: str) -> dict[str, Any] | None:
        response = self.session.get(
            self._url("/rest/api/content"),
            params={"spaceKey": space_id, "title": title, "expand": "version"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        return results[0] if results else None

    def create_page(
        self,
        *,
        space_id: str,
        parent_id: str,
        title: str,
        body_storage: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_id},
            "ancestors": [{"id": str(parent_id)}],
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        response = self.session.post(
            self._url("/rest/api/content"),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def update_page(
        self,
        *,
        page_id: str,
        title: str,
        body_storage: str,
        current_version: int,
    ) -> dict[str, Any]:
        payload = {
            "id": str(page_id),
            "type": "page",
            "title": title,
            "version": {"number": int(current_version) + 1},
            "body": {"storage": {"value": body_storage, "representation": "storage"}},
        }
        response = self.session.put(
            self._url(f"/rest/api/content/{page_id}"),
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def upload_attachment(self, *, page_id: str, path: Path, attachment_name: str) -> dict[str, Any]:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as file:
            response = self.session.post(
                self._url(f"/rest/api/content/{page_id}/child/attachment"),
                headers={"X-Atlassian-Token": "no-check"},
                files={"file": (attachment_name, file, content_type)},
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.json()

    def list_attachments(self, page_id: str, limit: int = 200) -> list[dict[str, Any]]:
        response = self.session.get(
            self._url(f"/rest/api/content/{page_id}/child/attachment"),
            params={"limit": limit},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def delete_attachment(self, attachment_id: str) -> None:
        response = self.session.delete(
            self._url(f"/rest/api/content/{attachment_id}"),
            timeout=self.timeout,
        )
        response.raise_for_status()

    def page_url(self, page: dict[str, Any]) -> str | None:
        links = page.get("_links", {})
        webui = links.get("webui")
        if isinstance(webui, str):
            return f"{self.base_url}{webui}"
        tiny = links.get("tinyui")
        if isinstance(tiny, str):
            return f"{self.base_url}{tiny}"
        page_id = page.get("id")
        return f"{self.base_url}/pages/viewpage.action?pageId={page_id}" if page_id else None

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"
