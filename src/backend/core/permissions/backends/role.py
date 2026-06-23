"""Role-based permissions backend."""

from django.db.models import Exists, OuterRef, Q

from lasuite.drf.models.choices import get_equivalent_link_definition

from core import models
from core.permissions.backends.base import PermissionsBackend


def _cut_by_restriction(path):
    """Build a subquery matching accesses separated from the given path by a restricted folder."""
    return Exists(
        models.Item.objects.filter(
            is_restricted=True,
            path__ancestors=path,
            path__descendants=OuterRef("item__path"),
        ).exclude(path=OuterRef("item__path"))
    )


class RolePermissionsBackend(PermissionsBackend):
    """Role-based engine inheriting roles along the item tree, stopping at restricted folders."""

    def effective_accesses(self, item):
        """Return the accesses applying to the item, down to its restriction boundary."""
        return models.ItemAccess.objects.filter(
            item__path__ancestors=item.path,
        ).exclude(_cut_by_restriction(item.path))

    def roles_at(self, user, path):
        """Return the roles the user holds at the given path, direct or inherited."""
        return (
            models.ItemAccess.objects.filter(
                Q(user=user) | Q(team__in=user.teams),
                item__path__ancestors=path,
            )
            .exclude(_cut_by_restriction(path))
            .values_list("role", flat=True)
        )

    def roles_for(self, user, item):
        """Return the roles the user holds on the item, direct or inherited."""
        if item.is_restricted:
            # Inheritance is cut on the item itself: only direct accesses apply
            return models.ItemAccess.objects.filter(
                Q(user=user) | Q(team__in=user.teams),
                item=item,
            ).values_list("role", flat=True)
        return self.roles_at(user, item.path)

    def ancestors_links_paths_mapping(self, item):
        """Return the link definitions applying to each ancestor path of the item."""
        ancestors = (
            (item.ancestors() | models.Item.objects.filter(pk=item.pk))
            .filter(ancestors_deleted_at__isnull=True)
            .order_by("path")
        )
        ancestors_links = []
        paths_links_mapping = {}

        for ancestor in ancestors:
            if ancestor.is_restricted:
                # Inheritance is cut: links from above the boundary do not apply
                ancestors_links = []
            ancestors_links.append(
                {"link_reach": ancestor.link_reach, "link_role": ancestor.link_role}
            )
            paths_links_mapping[str(ancestor.path)] = ancestors_links.copy()

        return paths_links_mapping

    def link_definition_for(self, item):
        """Return the effective link definition of the item, own and inherited combined."""
        if item.is_restricted:
            return item.link_definition
        return get_equivalent_link_definition(
            [item.ancestors_link_definition, item.link_definition]
        )
