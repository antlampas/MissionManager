# SPDX-License-Identifier: CC-BY-SA-4.0
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class PagedResult(Generic[T]):
    """Typed container for paginated list responses.

    Attributes:
        items:   Slice of results for the requested page.
        total:   Total number of items matching the query (across all pages).
        page:    1-based page number of this slice.
        page_size: Maximum items per page as requested.
    """

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return max(1, -(-self.total // self.page_size))

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1
