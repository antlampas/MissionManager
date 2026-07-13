# SPDX-License-Identifier: CC-BY-SA-4.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .exceptions import ValidationError


@dataclass(frozen=True)
class AssignmentPolicy:
    max_total: Optional[int] = None
    max_concurrent: Optional[int] = None

    def __post_init__(self) -> None:
        if self.max_total is not None and self.max_total < 1:
            raise ValidationError("max_total deve essere >= 1", field="max_total")
        if self.max_concurrent is not None and self.max_concurrent < 1:
            raise ValidationError("max_concurrent deve essere >= 1", field="max_concurrent")
        if (
            self.max_total is not None
            and self.max_concurrent is not None
            and self.max_total < self.max_concurrent
        ):
            raise ValidationError(
                "max_total deve essere >= max_concurrent",
                field="max_concurrent",
            )

    @staticmethod
    def unlimited() -> AssignmentPolicy:
        return AssignmentPolicy()

    @staticmethod
    def once() -> AssignmentPolicy:
        return AssignmentPolicy(max_total=1)

    @staticmethod
    def once_active() -> AssignmentPolicy:
        return AssignmentPolicy(max_concurrent=1)


# Il profilo di autorizzazione (Profile), le entry ACL e i riferimenti a
# soggetti/risorse vivono nel modulo dedicato ``domain.acl`` (DESIGN §10).
