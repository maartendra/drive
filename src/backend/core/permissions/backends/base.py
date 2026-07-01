"""Permissions Backend base class."""

from abc import ABC, abstractmethod

from django.db.models import prefetch_related_objects
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

    @abstractmethod
    def restriction_roots_below(self, item):
        """Return the restricted descendants not nested under another restricted folder."""

    @abstractmethod
    def annotate_roles(self, queryset, user, path_field="path"):
        """Annotate the queryset rows with the user's roles as user_roles."""

    @abstractmethod
    def propagation_scope(self, item):
        """Return the descendants of the item outside any restricted subtree."""

    @abstractmethod
    def inheritance_scope(self, item):
        """Return the ancestors of the item, itself included, down to its restriction boundary."""

    def visible(self, queryset, user, path_field="path"):
        """Filter the queryset to the rows on which the user holds a role."""
        if user and user.is_authenticated:
            prefetch_related_objects([user], "teams")
        return self.annotate_roles(queryset, user, path_field=path_field).exclude(user_roles=[])

    def role_at(self, user, path):
        """Return the highest role the user holds at the given path."""
        return RoleChoices.max(*self.roles_at(user, path))
