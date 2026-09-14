from __future__ import annotations

from contracts.ports import Source


class FakeSearch:
    async def search(self, query: str, n: int) -> list[Source]:
        return [
            Source(
                title=f"Source {i + 1} about {query}",
                url=f"https://example.org/{i + 1}",
                snippet=f"Canned finding {i + 1} on {query}.",
            )
            for i in range(n)
        ]
