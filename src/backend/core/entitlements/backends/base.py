"""Entitlements Backend base class."""

from abc import ABC, abstractmethod


class EntitlementsBackend(ABC):
    """Abstract base class for entitlements backends."""

    @abstractmethod
    def can_access(self, user):
        """
        Check if a user can access app.
        """

    @abstractmethod
    def can_upload(self, user):
        """
        Check if a user can upload a file.
        """

    def get_context(self, user):  # pylint: disable=unused-argument
        """Get context for a user."""
        return {}

    def get_quota(self, user):  # pylint: disable=unused-argument
        """Get quota for a user."""
        return {}