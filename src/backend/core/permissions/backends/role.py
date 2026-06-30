"""Role-based permissions backend."""

from django.conf import settings
from django.db.models import Exists, OuterRef, Q

from lasuite.drf.models.choices import (
    LinkReachChoices,
    RoleChoices,
    get_equivalent_link_definition,
)

from core import models
from core.permissions.backends.base import PermissionsBackend
from wopi.conversion.policy import target_extension_for


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

    def restriction_roots_below(self, item):
        """Return the restricted descendants not nested under another restricted folder."""
        return (
            item.descendants()
            .filter(is_restricted=True)
            .exclude(
                Exists(
                    models.Item.objects.filter(
                        is_restricted=True,
                        path__descendants=item.path,
                        path__ancestors=OuterRef("path"),
                    ).exclude(path=OuterRef("path"))
                )
            )
        )

    def abilities(self, user, item):  # pylint: disable=too-many-locals
        """Compute and return abilities for a given user on the item."""
        # First get the role based on specific access
        role = item.get_role(user)
        # Characteristics that are based only on specific access
        is_owner = role == RoleChoices.OWNER
        is_deleted = item.ancestors_deleted_at
        is_owner_or_admin = is_owner or role == RoleChoices.ADMIN

        # Compute access roles before adding link roles because we don't
        # want anonymous users to access versions (we wouldn't know from
        # which date to allow them anyway)
        # Anonymous users should also not see item accesses
        has_access_role = bool(role) and not is_deleted
        link_select_options = (
            LinkReachChoices.get_select_options(**item.ancestors_link_definition)
            if has_access_role
            else {}
        )

        link_definition = item.computed_link_definition

        link_reach = link_definition["link_reach"]
        if link_reach == LinkReachChoices.PUBLIC or (
            link_reach == LinkReachChoices.AUTHENTICATED and user.is_authenticated
        ):
            # Set the user role to the highest role between the item role and the link role
            # Needed for a user with an access lower than link_role
            # Needed for a user without access to determine the role he has.
            role = RoleChoices.max(role, link_definition["link_role"])
        can_get = bool(role) and not is_deleted
        retrieve = can_get or is_owner
        can_manage = is_owner_or_admin and not is_deleted
        can_update = (is_owner_or_admin or role == RoleChoices.EDITOR) and not is_deleted
        can_create_children = can_update and user.is_authenticated
        creator_can_delete = (
            user.is_authenticated
            and item.creator_id == user.id
            and (not item.is_restricted or has_access_role)
        )
        can_hard_delete = is_owner if item.is_root else (is_owner_or_admin or creator_can_delete)
        # Cheapest conditions first: the parent role check costs a query
        is_container_owner = False
        needs_container_owner_check = (
            not is_deleted
            and not can_get
            and not can_hard_delete
            and user.is_authenticated
            and item.is_restricted
            and item.depth > 1
        )
        if needs_container_owner_check:
            parent = (
                models.Item.objects.annotate_user_roles(user)
                .filter(path=str(item.path[:-1]))
                .first()
            )
            is_container_owner = parent is not None and parent.get_role(user) == RoleChoices.OWNER
        can_destroy = (can_hard_delete or is_container_owner) and not is_deleted
        can_duplicate = (
            can_get
            and user.is_authenticated
            and item.type == models.ItemTypeChoices.FILE
            and item.upload_state == models.ItemUploadStateChoices.READY
        )
        can_export = can_get and item.type == models.ItemTypeChoices.FOLDER
        can_convert = (
            can_update
            and item.type == models.ItemTypeChoices.FILE
            and item.upload_state
            in (
                models.ItemUploadStateChoices.READY,
                models.ItemUploadStateChoices.ANALYZING,
            )
            and bool(target_extension_for(item.extension))
            and bool(settings.WOPI_ONLYOFFICE_CONVERT_JWT_SECRET)
        )
        can_restrict = is_owner and not is_deleted and item.type == models.ItemTypeChoices.FOLDER

        return {
            "accesses_manage": can_manage,
            "accesses_view": has_access_role,
            "breadcrumb": can_get,
            "children_list": can_get,
            "children_create": can_create_children,
            "destroy": can_destroy,
            "download": can_get,
            "duplicate": can_duplicate,
            "export": can_export,
            "hard_delete": can_hard_delete,
            "favorite": can_get and user.is_authenticated,
            "link_configuration": can_manage,
            "invite_owner": is_owner and not is_deleted,
            "link_select_options": link_select_options,
            "move": can_manage,
            "restrict": can_restrict,
            "restore": is_owner,
            "retrieve": retrieve,
            "tree": can_get,
            "media_auth": can_get,
            "partial_update": can_update,
            "update": can_update,
            "upload_ended": can_update and user.is_authenticated,
            "wopi": can_get,
            "convert": can_convert,
        }
