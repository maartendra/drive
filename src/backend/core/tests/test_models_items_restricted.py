"""Tests for restricted folder model behavior."""

from django.core.exceptions import ValidationError

import pytest
from lasuite.drf.models.choices import LinkReachChoices

from core import factories, models

pytestmark = pytest.mark.django_db


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
