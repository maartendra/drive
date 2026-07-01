"""Tests for restricted folder model behavior."""

from django.core.exceptions import ValidationError

import pytest
from lasuite.drf.models.choices import LinkReachChoices

from core import factories, models

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,expected",
    [
        ("owner", True),
        ("administrator", False),
        ("editor", False),
        ("reader", False),
    ],
)
def test_models_items_restricted_get_abilities_restrict_requires_owner(role, expected):
    """Only an owner can restrict a folder."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=folder, user=user, role=role)

    abilities = folder.get_abilities(user)
    assert abilities["restrict"] is expected


def test_models_items_restricted_folder_can_be_restricted():
    """A folder can be restricted."""
    folder = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER, is_restricted=True)
    folder.refresh_from_db()
    assert folder.is_restricted is True


def test_models_items_restricted_file_cannot_be_restricted():
    """A file cannot be restricted."""
    with pytest.raises(ValidationError):
        factories.ItemFactory(type=models.ItemTypeChoices.FILE, is_restricted=True)


def test_models_items_restricted_nb_accesses_excludes_ancestors():
    """A restricted folder only counts the accesses that apply to it."""
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory.create_batch(2, item=parent)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder)

    assert folder.nb_accesses == 1


def test_models_items_restricted_nb_accesses_descendant_counts_from_boundary():
    """A descendant of a restricted folder counts accesses from the boundary only."""
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory.create_batch(2, item=parent)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder)
    child = factories.ItemFactory(parent=folder, type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=child)

    assert child.nb_accesses == 2


def test_models_items_restricted_activate_restriction_sets_flag_and_creates_owner_access():
    """Activating restriction sets is_restricted and creates an explicit owner access."""
    parent_user = factories.UserFactory()
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=parent_user, role="owner")
    folder = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FOLDER)

    assert folder.is_restricted is False
    assert not models.ItemAccess.objects.filter(item=folder, user=user).exists()

    folder.activate_restriction(user)
    folder.refresh_from_db()

    assert folder.is_restricted is True
    assert models.ItemAccess.objects.filter(item=folder, user=user, role="owner").exists()


def test_models_items_restricted_activate_restriction_keeps_existing_explicit_access():
    """Activating restriction does not duplicate an existing explicit owner access."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=folder, user=user, role="owner")

    folder.activate_restriction(user)
    folder.refresh_from_db()

    assert folder.is_restricted is True
    assert models.ItemAccess.objects.filter(item=folder, user=user, role="owner").count() == 1


def test_models_items_restricted_activate_restriction_promotes_existing_lower_access():
    """Activating restriction promotes an existing lower explicit access to owner."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    access = factories.UserItemAccessFactory(item=folder, user=user, role="reader")

    folder.activate_restriction(user)

    access.refresh_from_db()
    assert access.role == models.RoleChoices.OWNER


def test_models_items_restricted_activate_restriction_defaults_link_reach():
    """Activating restriction sets link reach to restricted when none is explicit."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="reader",
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        link_reach=None,
    )

    folder.activate_restriction(user)
    folder.refresh_from_db()

    assert folder.link_reach == LinkReachChoices.RESTRICTED


def test_models_items_restricted_deactivate_restriction_removes_redundant_access():
    """Deactivating restriction removes explicit accesses inferior or equal to inherited."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=user, role="editor")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert not models.ItemAccess.objects.filter(item=folder, user=user).exists()


def test_models_items_restricted_deactivate_restriction_keeps_superior_access():
    """Deactivating restriction keeps explicit accesses superior to inherited."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="reader")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=user, role="editor")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert models.ItemAccess.objects.filter(item=folder, user=user, role="editor").exists()


def test_models_items_restricted_deactivate_restriction_removes_redundant_team_access():
    """Deactivating restriction removes explicit team accesses inferior or equal to inherited."""
    team = "test-team"
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.TeamItemAccessFactory(item=parent, team=team, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.TeamItemAccessFactory(item=folder, team=team, role="editor")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert not models.ItemAccess.objects.filter(item=folder, team=team).exists()


def test_models_items_restricted_deactivate_restriction_keeps_superior_team_access():
    """Deactivating restriction keeps explicit team accesses superior to inherited."""
    team = "test-team"
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.TeamItemAccessFactory(item=parent, team=team, role="reader")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.TeamItemAccessFactory(item=folder, team=team, role="editor")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert models.ItemAccess.objects.filter(item=folder, team=team, role="editor").exists()


def test_models_items_restricted_deactivate_restriction_keeps_access_without_inheritance():
    """Deactivating restriction keeps explicit accesses when there is no inherited role."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=user, role="editor")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert models.ItemAccess.objects.filter(item=folder, user=user, role="editor").exists()


def test_models_items_restricted_deactivate_restriction_removes_equal_access():
    """Deactivating restriction removes explicit access equal to inherited role."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=user, role="owner")

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert not models.ItemAccess.objects.filter(item=folder, user=user).exists()


def test_models_items_restricted_deactivate_restriction_resets_redundant_link_reach():
    """Deactivating restriction resets link reach when inferior or equal to inherited."""
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.link_reach == LinkReachChoices.RESTRICTED
    assert folder.link_role == "reader"


def test_models_items_restricted_deactivate_restriction_keeps_superior_link_reach():
    """Deactivating restriction keeps link reach when superior to inherited."""
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.link_reach == LinkReachChoices.PUBLIC
    assert folder.link_role == "editor"


def test_models_items_restricted_deactivate_restriction_keeps_link_reach_without_ancestors():
    """Deactivating restriction keeps link reach on a root folder with no ancestors."""
    folder = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )

    folder.deactivate_restriction()
    folder.refresh_from_db()

    assert folder.is_restricted is False
    assert folder.link_reach == LinkReachChoices.AUTHENTICATED
    assert folder.link_role == "reader"


def test_models_items_restricted_uproot_moves_to_root():
    """Uprooting a restricted folder moves it to root with its accesses intact."""
    owner = factories.UserFactory()
    shared_user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=owner, role="owner")
    factories.UserItemAccessFactory(item=folder, user=shared_user, role="editor")

    folder.uproot()
    folder.refresh_from_db()

    assert folder.depth == 1
    assert models.ItemAccess.objects.filter(item=folder, user=owner, role="owner").exists()
    assert models.ItemAccess.objects.filter(item=folder, user=shared_user, role="editor").exists()


def test_models_items_restricted_uproot_moves_descendants():
    """Uprooting a restricted folder moves its descendants along with it."""
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    child = factories.ItemFactory(parent=folder, type=models.ItemTypeChoices.FOLDER)
    grandchild = factories.ItemFactory(parent=child, type=models.ItemTypeChoices.FILE)

    folder.uproot()
    child.refresh_from_db()
    grandchild.refresh_from_db()

    assert child.depth == 2
    assert grandchild.depth == 3


def test_models_items_restricted_soft_delete_extracts_restricted_descendants():
    """Soft-deleting a folder extracts its shallowest restricted descendants to root."""
    root = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    normal_child = factories.ItemFactory(parent=root, type=models.ItemTypeChoices.FOLDER)
    restricted_child = factories.ItemFactory(
        parent=root,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    nested_restricted = factories.ItemFactory(
        parent=restricted_child,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )

    root.soft_delete()

    root.refresh_from_db()
    normal_child.refresh_from_db()
    restricted_child.refresh_from_db()
    nested_restricted.refresh_from_db()

    # Root and normal child are soft-deleted
    assert root.deleted_at is not None
    assert normal_child.ancestors_deleted_at is not None

    # Shallowest restricted child is extracted to root
    assert restricted_child.depth == 1
    assert restricted_child.deleted_at is None
    assert restricted_child.ancestors_deleted_at is None

    # Nested restricted stays inside the extracted folder
    assert nested_restricted.depth == 2
    assert nested_restricted.deleted_at is None
    assert nested_restricted.ancestors_deleted_at is None


def test_models_items_restricted_annotate_user_roles_blocks_inheritance():
    """Annotated user roles do not leak through a restriction boundary."""
    user = factories.UserFactory()
    grandparent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=grandparent, user=user, role="owner")
    parent = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FILE)

    annotated_child = models.Item.objects.annotate_user_roles(user).get(pk=child.pk)
    assert annotated_child.get_role(user) is None


@pytest.mark.parametrize("role", models.RoleChoices.values)
def test_models_items_restricted_get_role_ignores_ancestors(role):
    """No inherited role, regardless of level, produces access on a restricted child."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role=role)
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FOLDER)

    assert child.get_role(user) == role

    child.is_restricted = True

    assert child.get_role(user) is None


def test_models_items_restricted_get_role_uses_explicit_value():
    """Effective role on a restricted folder equals the explicit role, not the inherited one."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=child, user=user, role="reader")

    assert child.get_role(user) == "owner"

    child.is_restricted = True

    assert child.get_role(user) == "reader"


def test_models_items_restricted_get_role_blocks_inheritance_for_descendants():
    """A descendant of a restricted folder does not inherit roles from above the boundary."""
    user = factories.UserFactory()
    grandparent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=grandparent, user=user, role="owner")
    parent = factories.ItemFactory(parent=grandparent, type=models.ItemTypeChoices.FOLDER)
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FOLDER)

    assert child.get_role(user) == "owner"

    parent.is_restricted = True
    parent.save()

    assert child.get_role(user) is None


def test_models_items_restricted_get_role_descendant_inherits_from_restricted_folder():
    """A descendant inherits the explicit role set on the restricted folder."""
    user = factories.UserFactory()
    grandparent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=grandparent, user=user, role="owner")
    parent = factories.ItemFactory(parent=grandparent, type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="editor")
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FOLDER)

    assert child.get_role(user) == "owner"

    parent.is_restricted = True
    parent.save()

    assert child.get_role(user) == "editor"


def test_models_items_restricted_computed_link_definition_ignores_ancestors():
    """A restricted folder ignores ancestor link definition."""
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )
    child = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.RESTRICTED,
    )

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.PUBLIC,
        "link_role": "editor",
    }

    child.is_restricted = True
    child._computed_link_definition = None  # pylint: disable=protected-access

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.RESTRICTED,
        "link_role": "reader",
    }


def test_models_items_restricted_computed_link_definition_uses_explicit_value():
    """Computed link definition on a restricted folder equals its own explicit value."""
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )
    child = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.PUBLIC,
        "link_role": "editor",
    }

    child.is_restricted = True
    child._computed_link_definition = None  # pylint: disable=protected-access

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.AUTHENTICATED,
        "link_role": "reader",
    }


def test_models_items_restricted_computed_link_definition_blocks_inheritance_for_descendants():
    """A descendant of a restricted folder does not inherit link definitions from above."""
    grandparent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )
    parent = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )
    child = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.RESTRICTED,
    )

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.AUTHENTICATED,
        "link_role": "reader",
    }


def test_models_items_restricted_computed_link_definition_descendant_inherits_from_restricted():
    """A descendant inherits the link definition of its restricted ancestor, not above."""
    grandparent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.PUBLIC,
        link_role="editor",
    )
    parent = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="reader",
    )
    child = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        link_reach=LinkReachChoices.AUTHENTICATED,
        link_role="editor",
    )

    assert child.computed_link_definition == {
        "link_reach": LinkReachChoices.AUTHENTICATED,
        "link_role": "editor",
    }


def test_models_items_restricted_get_abilities_container_owner_can_destroy():
    """Owner of parent folder can destroy a restricted child they have no access to."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )

    abilities = folder.get_abilities(user)
    assert abilities["destroy"] is True
    assert abilities["hard_delete"] is False
    assert abilities["retrieve"] is False
    assert abilities["partial_update"] is False
    assert abilities["move"] is False


def test_models_items_restricted_get_abilities_container_owner_via_team(mock_user_teams):
    """Owner of parent folder via team access can destroy a restricted child."""
    user = factories.UserFactory()
    mock_user_teams.return_value = ["team-alpha"]
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    models.ItemAccess.objects.create(item=parent, team="team-alpha", role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )

    abilities = folder.get_abilities(user)
    assert abilities["destroy"] is True


def test_models_items_restricted_get_abilities_intermediate_restriction_blocks_destroy():
    """Owner above an intermediate restriction cannot destroy a nested restricted folder."""
    user = factories.UserFactory()
    grandparent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=grandparent, user=user, role="owner")
    parent = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )

    abilities = folder.get_abilities(user)
    assert abilities["destroy"] is False


def test_models_items_restricted_get_abilities_explicit_owner_normal_destroy():
    """Explicit owner of a restricted folder gets normal destroy with hard_delete."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=user, role="owner")

    abilities = folder.get_abilities(user)
    assert abilities["destroy"] is True
    assert abilities["hard_delete"] is True


def test_models_items_restricted_get_abilities_excluded_creator_cannot_destroy():
    """Creator excluded from a restricted folder cannot destroy it without parent ownership."""
    creator = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        creator=creator,
    )

    abilities = folder.get_abilities(creator)
    assert abilities["destroy"] is False
    assert abilities["hard_delete"] is False


def test_models_items_restricted_get_abilities_container_owner_cannot_destroy_deleted():
    """Container owner cannot destroy a soft-deleted restricted folder."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        deleted_at="2025-01-01T00:00:00Z",
        ancestors_deleted_at="2025-01-01T00:00:00Z",
    )

    abilities = folder.get_abilities(user)
    assert abilities["destroy"] is False


def test_models_items_restricted_deactivation_stops_at_boundary():
    """Normalization must not use accesses above another restricted boundary."""
    user = factories.UserFactory()
    grandparent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, models.RoleChoices.OWNER)],
    )
    parent = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(
        item=folder,
        user=user,
        role=models.RoleChoices.READER,
    )

    folder.deactivate_restriction()

    assert models.ItemAccess.objects.filter(
        item=folder,
        user=user,
        role=models.RoleChoices.READER,
    ).exists()
