"""Role-based permissions backend."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.postgres.fields import ArrayField
from django.db.models import CharField, Exists, Func, OuterRef, Q, QuerySet, Value
from django.utils.functional import cached_property

from lasuite.drf.models.choices import (
    LinkReachChoices,
    RoleChoices,
    get_equivalent_link_definition,
)

from core import models
from core.permissions.backends.base import PermissionsBackend
from wopi.conversion.policy import target_extension_for


def _cut_by_restriction(path, path_field="item__path"):
    """Build a subquery matching rows separated from the given path by a restricted folder."""
    return Exists(
        models.Item.objects.filter(
            is_restricted=True,
            path__ancestors=path,
            path__descendants=OuterRef(path_field),
        ).exclude(path=OuterRef(path_field))
    )


class ItemAbilities:  # pylint: disable=too-many-public-methods
    """Compute the abilities of a user on an item, one property per ability."""

    def __init__(self, user: models.User | AnonymousUser, item: models.Item) -> None:
        self.user = user
        self.item = item

    @cached_property
    def access_role(self):
        """Return the role held through accesses only, before any link boost."""
        return self.item.get_role(self.user)

    @cached_property
    def role(self):
        """Return the effective role, link definition included."""
        link_definition = self.item.computed_link_definition
        link_reach = link_definition["link_reach"]
        if link_reach == LinkReachChoices.PUBLIC or (
            link_reach == LinkReachChoices.AUTHENTICATED and self.user.is_authenticated
        ):
            # The highest of the access role and the link role, needed for a user
            # with an access lower than the link role and for a user without access
            return RoleChoices.max(self.access_role, link_definition["link_role"])
        return self.access_role

    @cached_property
    def is_deleted(self):
        """Return whether the item or one of its ancestors is soft deleted."""
        return bool(self.item.ancestors_deleted_at)

    @cached_property
    def is_owner(self):
        """Return whether the user holds an owner role through accesses."""
        return self.access_role == RoleChoices.OWNER

    @cached_property
    def is_owner_or_admin(self):
        """Return whether the user holds an owner or administrator role through accesses."""
        return self.is_owner or self.access_role == RoleChoices.ADMIN

    @cached_property
    def has_access_role(self):
        """Return whether the user holds a role through accesses on a live item."""
        # Based on accesses only so that anonymous users granted by a link
        # cannot see item accesses or versions
        return bool(self.access_role) and not self.is_deleted

    @cached_property
    def link_select_options(self):
        """Return the link reach and role options selectable on the item."""
        if not self.has_access_role:
            return {}
        return LinkReachChoices.get_select_options(**self.item.ancestors_link_definition)

    @property
    def can_get(self):
        """Return whether the user can read the item."""
        return bool(self.role) and not self.is_deleted

    @property
    def can_retrieve(self):
        """Return whether the user can retrieve the item, even soft deleted."""
        return self.can_get or self.is_owner

    @property
    def can_manage(self):
        """Return whether the user can manage the item and its accesses."""
        return self.is_owner_or_admin and not self.is_deleted

    @property
    def can_update(self):
        """Return whether the user can modify the item."""
        return (self.is_owner_or_admin or self.role == RoleChoices.EDITOR) and not self.is_deleted

    @property
    def can_create_children(self):
        """Return whether the user can create children in the item."""
        return self.can_update and self.user.is_authenticated

    @cached_property
    def can_hard_delete(self):
        """Return whether the user can delete the item permanently."""
        if self.item.is_root:
            return self.is_owner
        creator_can_delete = (
            self.user.is_authenticated
            and self.item.creator_id == self.user.id
            and (not self.item.is_restricted or self.has_access_role)
        )
        return self.is_owner_or_admin or creator_can_delete

    @cached_property
    def is_container_owner(self):
        """Return whether the user owns the folder containing this restricted item."""
        # Cheapest conditions first: the parent role check costs a query
        needs_parent_check = (
            not self.is_deleted
            and not self.can_get
            and not self.can_hard_delete
            and self.user.is_authenticated
            and self.item.is_restricted
            and self.item.depth > 1
        )
        if not needs_parent_check:
            return False
        parent = (
            models.Item.objects.annotate_user_roles(self.user)
            .filter(path=str(self.item.path[:-1]))
            .first()
        )
        return parent is not None and parent.get_role(self.user) == RoleChoices.OWNER

    @property
    def can_destroy(self):
        """Return whether the user can remove the item, by deletion or uprooting."""
        return (self.can_hard_delete or self.is_container_owner) and not self.is_deleted

    @property
    def can_duplicate(self):
        """Return whether the user can duplicate the file."""
        return (
            self.can_get
            and self.user.is_authenticated
            and self.item.type == models.ItemTypeChoices.FILE
            and self.item.upload_state == models.ItemUploadStateChoices.READY
        )

    @property
    def can_export(self):
        """Return whether the user can export the folder as an archive."""
        return self.can_get and self.item.type == models.ItemTypeChoices.FOLDER

    @property
    def can_convert(self):
        """Return whether the user can convert the file to another format."""
        return (
            self.can_update
            and self.item.type == models.ItemTypeChoices.FILE
            and self.item.upload_state
            in (
                models.ItemUploadStateChoices.READY,
                models.ItemUploadStateChoices.ANALYZING,
            )
            and bool(target_extension_for(self.item.extension))
            and bool(settings.WOPI_ONLYOFFICE_CONVERT_JWT_SECRET)
        )

    @property
    def can_restrict(self):
        """Return whether the user can restrict the folder."""
        return (
            self.is_owner
            and not self.is_deleted
            and self.item.type == models.ItemTypeChoices.FOLDER
        )

    @property
    def can_favorite(self):
        """Return whether the user can mark the item as favorite."""
        return self.can_get and self.user.is_authenticated

    @property
    def can_invite_owner(self):
        """Return whether the user can invite another owner on the item."""
        return self.is_owner and not self.is_deleted

    @property
    def can_restore(self):
        """Return whether the user can restore the item from the trash."""
        return self.is_owner

    @property
    def can_upload_ended(self):
        """Return whether the user can mark an upload on the item as ended."""
        return self.can_update and self.user.is_authenticated

    def as_dict(self) -> dict[str, bool | dict]:
        """Return the ability mapping exposed by the API."""
        return {
            "accesses_manage": self.can_manage,
            "accesses_view": self.has_access_role,
            "breadcrumb": self.can_get,
            "children_list": self.can_get,
            "children_create": self.can_create_children,
            "destroy": self.can_destroy,
            "download": self.can_get,
            "duplicate": self.can_duplicate,
            "export": self.can_export,
            "hard_delete": self.can_hard_delete,
            "favorite": self.can_favorite,
            "link_configuration": self.can_manage,
            "invite_owner": self.can_invite_owner,
            "link_select_options": self.link_select_options,
            "move": self.can_manage,
            "restrict": self.can_restrict,
            "restore": self.can_restore,
            "retrieve": self.can_retrieve,
            "tree": self.can_get,
            "media_auth": self.can_get,
            "partial_update": self.can_update,
            "update": self.can_update,
            "upload_ended": self.can_upload_ended,
            "wopi": self.can_get,
            "convert": self.can_convert,
        }


class RolePermissionsBackend(PermissionsBackend):
    """Role-based engine inheriting roles along the item tree, stopping at restricted folders."""

    def effective_accesses(self, item: models.Item) -> QuerySet[models.ItemAccess]:
        """Return the accesses applying to the item, down to its restriction boundary."""
        return models.ItemAccess.objects.filter(
            item__path__ancestors=item.path,
        ).exclude(_cut_by_restriction(item.path))

    def roles_at(self, user: models.User, path: str) -> QuerySet[str]:
        """Return the roles the user holds at the given path, direct or inherited."""
        return (
            models.ItemAccess.objects.filter(
                Q(user=user) | Q(team__in=user.teams),
                item__path__ancestors=path,
            )
            .exclude(_cut_by_restriction(path))
            .values_list("role", flat=True)
        )

    def roles_for(self, user: models.User, item: models.Item) -> QuerySet[str]:
        """Return the roles the user holds on the item, direct or inherited."""
        if item.is_restricted:
            # Inheritance is cut on the item itself: only direct accesses apply
            return models.ItemAccess.objects.filter(
                Q(user=user) | Q(team__in=user.teams),
                item=item,
            ).values_list("role", flat=True)
        return self.roles_at(user, item.path)

    def ancestors_links_paths_mapping(self, item: models.Item) -> dict[str, list[dict[str, str]]]:
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

    def link_definition_for(self, item: models.Item) -> dict[str, str]:
        """Return the effective link definition of the item, own and inherited combined."""
        if item.is_restricted:
            return item.link_definition
        return get_equivalent_link_definition(
            [item.ancestors_link_definition, item.link_definition]
        )

    def annotate_roles(
        self,
        queryset: QuerySet[models.Item],
        user: models.User | AnonymousUser,
        path_field: str = "path",
    ) -> QuerySet[models.Item]:
        """Annotate the queryset rows with the user's roles as user_roles."""
        output_field = ArrayField(base_field=CharField())

        if user.is_authenticated:
            user_roles_subquery = (
                models.ItemAccess.objects.filter(
                    Q(user=user) | Q(team__in=user.teams),
                    item__path__ancestors=OuterRef(path_field),
                )
                .exclude(_cut_by_restriction(OuterRef(OuterRef(path_field))))
                .values_list("role", flat=True)
            )

            return queryset.annotate(
                user_roles=Func(user_roles_subquery, function="ARRAY", output_field=output_field)
            )

        return queryset.annotate(user_roles=Value([], output_field=output_field))

    def inheritance_scope(self, item: models.Item) -> QuerySet[models.Item]:
        """Return the ancestors of the item, itself included, down to its restriction boundary."""
        return models.Item.objects.filter(path__ancestors=item.path).exclude(
            _cut_by_restriction(item.path, path_field="path")
        )

    def propagation_scope(self, item: models.Item) -> QuerySet[models.Item]:
        """Return the descendants of the item outside any restricted subtree."""
        return item.descendants().exclude(
            Exists(
                models.Item.objects.filter(
                    is_restricted=True,
                    path__descendants=item.path,
                    path__ancestors=OuterRef("path"),
                )
            )
        )

    def restriction_roots_below(self, item: models.Item) -> QuerySet[models.Item]:
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

    def abilities(
        self, user: models.User | AnonymousUser, item: models.Item
    ) -> dict[str, bool | dict]:
        """Compute and return abilities for a given user on the item."""
        return ItemAbilities(user, item).as_dict()
