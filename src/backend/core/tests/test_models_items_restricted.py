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
