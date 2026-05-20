"""SearchClient Protocol + Brave Search + MockSearchClient. See ADR-0011/0018/0021."""
from __future__ import annotations

import os
from typing import Protocol

import httpx
from pydantic import BaseModel


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class SearchClient(Protocol):
    async def search(self, query: str, n: int) -> list[SearchResult]: ...


class MockSearchClient:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self._results: list[SearchResult] = results or []

    async def search(self, query: str, n: int) -> list[SearchResult]:
        return self._results[:n]


class BraveSearchClient:
    _BASE = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        self.__api_key = api_key  # private — never logged or repr'd

    def __repr__(self) -> str:
        return "BraveSearchClient(<key redacted>)"

    async def search(self, query: str, n: int = 5) -> list[SearchResult]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(
                self._BASE,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.__api_key,
                },
                params={"q": query, "count": min(n, 20)},
            )
            r.raise_for_status()
            hits = r.json().get("web", {}).get("results", [])
        return [
            SearchResult(title=h["title"], url=h["url"], snippet=h.get("description", ""))
            for h in hits[:n]
        ]


_QUICK_STUB_RESULTS: list[SearchResult] = [
    SearchResult(
        title="Coursera - Online Courses",
        url="https://coursera.org",
        snippet="Online learning marketplace with AI recommendations",
    ),
    SearchResult(
        title="Wyzant - Tutor Marketplace",
        url="https://wyzant.com",
        snippet="Connect with expert tutors for personalised learning",
    ),
    SearchResult(
        title="Chegg Tutors",
        url="https://chegg.com",
        snippet="On-demand tutoring and homework help",
    ),
    SearchResult(
        title="Preply - Language Tutoring",
        url="https://preply.com",
        snippet="AI-matched tutors for language learning",
    ),
    SearchResult(
        title="Superprof - Tutor Network",
        url="https://superprof.com",
        snippet="Largest network of tutors worldwide",
    ),
]


def make_search(depth: str) -> SearchClient:
    """Factory per ADR-0021 Residual 3.

    depth=quick always returns MockSearchClient.
    depth=standard|deep requires BRAVE_API_KEY; raises RuntimeError if absent.
    """
    if depth == "quick":
        return MockSearchClient(results=_QUICK_STUB_RESULTS)
    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        raise RuntimeError("BRAVE_API_KEY not set; use --depth quick for offline runs")
    return BraveSearchClient(key)
