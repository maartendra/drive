"""Permissions Backend base class."""

from abc import ABC, abstractmethod

from lasuite.drf.models.choices import RoleChoices


class PermissionsBackend(ABC):
    """Abstract base class for item permissions backends."""

    @abstractmethod
    def effective_accesses(self, item):
        """Return the accesses applying to the item, direct or inherited."""

    @abstractmethod
    def roles_at(self, user, path):
        """Return the roles the user holds at the given path, direct or inherited."""

    @abstractmethod
    def roles_for(self, user, item):
        """Return the roles the user holds on the item, direct or inherited."""

    def role_at(self, user, path):
        """Return the highest role the user holds at the given path."""
        return RoleChoices.max(*self.roles_at(user, path))
