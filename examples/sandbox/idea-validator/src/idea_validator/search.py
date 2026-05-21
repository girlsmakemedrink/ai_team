"""SearchClient Protocol, MockSearchClient, BraveSearchClient, factory (ADR-0019)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


@runtime_checkable
class SearchClient(Protocol):
    async def search(self, query: str, n: int = 5) -> list[SearchResult]: ...


class MockSearchClient:
    def __init__(
        self,
        results: list[SearchResult] | None = None,
        fixture_dir: Path | None = None,
    ) -> None:
        self._results = results or []
        self._fixture_dir = fixture_dir

    async def search(self, query: str, n: int = 5) -> list[SearchResult]:
        if self._results:
            return self._results[:n]
        if self._fixture_dir:
            import json
            f = self._fixture_dir / "results.json"
            if f.exists():
                data = json.loads(f.read_text())
                return [SearchResult(**r) for r in data[:n]]
        return [
            SearchResult(title=f"Mock Co {i}", url=f"https://mock{i}.example.com", snippet="snippet")
            for i in range(min(n, 3))
        ]


class BraveSearchClient:
    def __init__(self, api_key: str, http_client: Any) -> None:
        self.__api_key = api_key
        self._http = http_client

    async def search(self, query: str, n: int = 5) -> list[SearchResult]:
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {"Accept": "application/json", "X-Subscription-Token": self.__api_key}
        resp = await self._http.get(url, params={"q": query, "count": n}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("web", {}).get("results", [])
        return [
            SearchResult(title=r["title"], url=r["url"], snippet=r.get("description", ""))
            for r in results[:n]
        ]


def make_search(depth: str) -> SearchClient:
    if depth == "quick":
        return MockSearchClient(
            fixture_dir=Path(__file__).parent.parent.parent / "tests" / "fixtures" / "search"
        )
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_API_KEY not set; use --depth quick for offline runs")
    import httpx
    return BraveSearchClient(api_key=key, http_client=httpx.AsyncClient(timeout=30.0))
