from __future__ import annotations

from abc import ABC, abstractmethod


class Observer(ABC):
    @abstractmethod
    def on_node_start(self, *, job_id: str, node_id: str, node_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def on_node_complete(self, *, job_id: str, node_id: str, node_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def on_node_failed(self, *, job_id: str, node_id: str, node_name: str, error: str) -> None:
        raise NotImplementedError

    def on_node_page_complete(
        self,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        page_index: int,
        page_count: int,
    ) -> None:
        """Called when one page finishes a page-scoped node (streaming pipeline).

        Non-abstract with a no-op default so existing observers keep working; page
        aware observers (progress) override it to advance per-page progress.
        """
        return None

    def on_node_page_start(
        self,
        *,
        job_id: str,
        node_id: str,
        node_name: str,
        page_index: int,
        page_count: int,
    ) -> None:
        """Called immediately before a page-scoped node starts for one page."""
        return None
