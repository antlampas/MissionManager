# SPDX-License-Identifier: CC-BY-SA-4.0
"""In-memory adapters intended for tests and local development."""

from auth.infrastructure.memory.repositories import InMemoryAuthRepository

__all__ = ["InMemoryAuthRepository"]
