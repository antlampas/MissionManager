# SPDX-License-Identifier: CC-BY-SA-4.0
"""Fail-closed registry for installable access-control model extensions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from auth.domain.access_control import AccessControlModelExtension
from auth.domain.errors import ConfigurationError


class DefaultAccessControlModelRegistry:
    def __init__(
        self,
        active_model_id: str,
        models: Iterable[AccessControlModelExtension] = (),
        *,
        providers: Mapping[str, object] | None = None,
        settings: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        if not active_model_id:
            raise ConfigurationError("access_control.model is required")
        self._active_model_id = active_model_id
        self._models: dict[str, AccessControlModelExtension] = {}
        self._providers = dict(providers or {})
        self._settings = dict(settings or {})
        for model in models:
            self.register(model)
        self.validate_active()

    def register(self, model: AccessControlModelExtension) -> None:
        if not model.id:
            raise ConfigurationError("access-control model id is required")
        if model.id in self._models:
            raise ConfigurationError(f"duplicate access-control model: {model.id}")
        self._models[model.id] = model

    def active(self) -> AccessControlModelExtension:
        try:
            return self._models[self._active_model_id]
        except KeyError as exc:
            raise ConfigurationError(f"active access-control model is not registered: {self._active_model_id}") from exc

    def get(self, model_id: str) -> AccessControlModelExtension | None:
        return self._models.get(model_id)

    def validate_active(self) -> None:
        model = self.active()
        missing = sorted(model.required_providers - self._providers.keys())
        if missing:
            raise ConfigurationError(f"missing providers for access-control model {model.id}: {', '.join(missing)}")
        model.validate_config(self._settings.get(model.id, {}))
