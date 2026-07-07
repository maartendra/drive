"""Permissions backend factory."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils.module_loading import import_string

if TYPE_CHECKING:
    from core.permissions.backends.base import PermissionsBackend


@functools.cache
def get_permissions_backend() -> PermissionsBackend:
    """Get the permissions backend."""
    return import_string(settings.PERMISSIONS_BACKEND)(**settings.PERMISSIONS_BACKEND_PARAMETERS)
