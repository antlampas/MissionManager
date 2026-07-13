# SPDX-License-Identifier: CC-BY-SA-4.0
from abc import ABC, abstractmethod

from ..domain.plugins import HookContext, PluginManifest


class MissionHookAdapter(ABC):
    """Base astratta per i plugin hook concreti.

    Le implementazioni concrete estendono questa classe e registrano
    i propri HookPoint nel manifest. Esempio: ExternalSyncHook si
    registra su AFTER_UPDATE_STATUS e invia i dati di completamento
    a un sistema esterno via HTTP.
    """

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest: ...

    @abstractmethod
    def execute(self, context: HookContext) -> None: ...
