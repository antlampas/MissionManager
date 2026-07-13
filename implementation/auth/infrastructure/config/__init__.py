# SPDX-License-Identifier: CC-BY-SA-4.0
"""Configuration and composition root helpers."""

from auth.infrastructure.config.bootstrap import bootstrap_auth
from auth.infrastructure.config.settings import AuthSettings

__all__ = ["AuthSettings", "bootstrap_auth"]
