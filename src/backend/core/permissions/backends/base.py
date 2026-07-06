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

    @abstractmethod
    def ancestors_links_paths_mapping(self, item):
        """Return the link definitions applying to each ancestor path of the item."""

    @abstractmethod
    def link_definition_for(self, item):
        """Return the effective link definition of the item, own and inherited combined."""

    @abstractmethod
    def abilities(self, user, item):
        """Compute and return abilities for a given user on the item."""

    def role_at(self, user, path):
        """Return the highest role the user holds at the given path."""
        return RoleChoices.max(*self.roles_at(user, path))
