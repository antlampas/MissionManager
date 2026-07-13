# SPDX-License-Identifier: CC-BY-SA-4.0
from typing import Protocol, runtime_checkable

from ..domain.entities import Person


@runtime_checkable
class OperatorIdentityProvider(Protocol):
    def get_current_operator(self) -> Person: ...
