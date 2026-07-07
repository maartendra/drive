"""Permissions Backend base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from django.contrib.auth.models import AnonymousUser
from django.db.models import QuerySet

from lasuite.drf.models.choices import RoleChoices

if TYPE_CHECKING:
    from core import models


class PermissionsBackend(ABC):
    """Abstract base class for item permissions backends."""

    @abstractmethod
    def effective_accesses(self, item: models.Item) -> QuerySet[models.ItemAccess]:
        """Return the accesses applying to the item, direct or inherited."""

    @abstractmethod
    def roles_at(self, user: models.User, path: str) -> QuerySet[str]:
        """Return the roles the user holds at the given path, direct or inherited."""

    @abstractmethod
    def roles_for(self, user: models.User, item: models.Item) -> QuerySet[str]:
        """Return the roles the user holds on the item, direct or inherited."""

    @abstractmethod
    def ancestors_links_paths_mapping(self, item: models.Item) -> dict[str, list[dict[str, str]]]:
        """Return the link definitions applying to each ancestor path of the item."""

    @abstractmethod
    def link_definition_for(self, item: models.Item) -> dict[str, str]:
        """Return the effective link definition of the item, own and inherited combined."""

    @abstractmethod
    def abilities(
        self, user: models.User | AnonymousUser, item: models.Item
    ) -> dict[str, bool | dict]:
        """Compute and return abilities for a given user on the item."""

    @abstractmethod
    def restriction_roots_below(self, item: models.Item) -> QuerySet[models.Item]:
        """Return the restricted descendants not nested under another restricted folder."""

    @abstractmethod
    def annotate_roles(
        self,
        queryset: QuerySet[models.Item],
        user: models.User | AnonymousUser,
        path_field: str = "path",
    ) -> QuerySet[models.Item]:
        """Annotate the queryset rows with the user's roles as user_roles."""

    @abstractmethod
    def propagation_scope(self, item: models.Item) -> QuerySet[models.Item]:
        """Return the descendants of the item outside any restricted subtree."""

    @abstractmethod
    def inheritance_scope(self, item: models.Item) -> QuerySet[models.Item]:
        """Return the ancestors of the item, itself included, down to its restriction boundary."""

    def visible(
        self,
        queryset: QuerySet[models.Item],
        user: models.User | AnonymousUser,
        path_field: str = "path",
    ) -> QuerySet[models.Item]:
        """Filter the queryset to the rows on which the user holds a role."""
        return self.annotate_roles(queryset, user, path_field=path_field).exclude(user_roles=[])

    def role_at(self, user: models.User, path: str) -> str | None:
        """Return the highest role the user holds at the given path."""
        return RoleChoices.max(*self.roles_at(user, path))
