"""Tests for items API endpoint: restrict / unrestrict via partial update."""

import pytest
from rest_framework.test import APIClient

from core import factories, models

pytestmark = pytest.mark.django_db


def test_api_items_restrict_owner_can_activate():
    """An owner can activate restriction on a folder via partial update."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, "owner")],
    )

    client = APIClient()
    client.force_login(user)

    response = client.patch(
        f"/api/v1.0/items/{folder.id!s}/",
        {"is_restricted": True},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["is_restricted"] is True

    folder.refresh_from_db()
    assert folder.is_restricted is True
    assert models.ItemAccess.objects.filter(item=folder, user=user, role="owner").count() == 1


def test_api_items_restrict_non_owner_cannot_activate():
    """A non-owner cannot activate restriction on a folder."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, "administrator")],
    )

    client = APIClient()
    client.force_login(user)

    response = client.patch(
        f"/api/v1.0/items/{folder.id!s}/",
        {"is_restricted": True},
        format="json",
    )
    assert response.status_code == 403

    folder.refresh_from_db()
    assert folder.is_restricted is False


def test_api_items_restrict_owner_can_deactivate():
    """An owner can deactivate restriction on a folder via partial update."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(type=models.ItemTypeChoices.FOLDER)
    factories.UserItemAccessFactory(item=parent, user=user, role="owner")
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        users=[(user, "owner")],
    )

    client = APIClient()
    client.force_login(user)

    response = client.patch(
        f"/api/v1.0/items/{folder.id!s}/",
        {"is_restricted": False},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["is_restricted"] is False

    folder.refresh_from_db()
    assert folder.is_restricted is False


def test_api_items_restrict_response_includes_field():
    """The is_restricted field is present in the API response."""
    user = factories.UserFactory()
    folder = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, "owner")],
    )

    client = APIClient()
    client.force_login(user)

    response = client.get(f"/api/v1.0/items/{folder.id!s}/")
    assert response.status_code == 200
    assert "is_restricted" in response.json()
    assert response.json()["is_restricted"] is False


def test_api_items_restrict_delete_by_container_owner_uproots():
    """DELETE by container owner moves the restricted folder to root instead of trashing it."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, "owner")],
    )
    child = factories.ItemFactory(parent=parent, type=models.ItemTypeChoices.FILE)
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    factories.UserItemAccessFactory(item=folder, user=factories.UserFactory(), role="owner")
    descendant = factories.ItemFactory(parent=folder, type=models.ItemTypeChoices.FILE)

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/items/{folder.id!s}/")
    assert response.status_code == 204

    folder.refresh_from_db()
    assert folder.deleted_at is None
    assert folder.depth == 1
    assert folder.is_restricted is True

    descendant.refresh_from_db()
    assert descendant.deleted_at is None
    assert descendant.depth == 2

    child.refresh_from_db()
    assert child.deleted_at is None


def test_api_items_restrict_delete_by_explicit_owner_soft_deletes():
    """DELETE by explicit owner of a restricted folder soft-deletes it normally."""
    user = factories.UserFactory()
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(user, "owner")],
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        users=[(user, "owner")],
    )

    client = APIClient()
    client.force_login(user)

    response = client.delete(f"/api/v1.0/items/{folder.id!s}/")
    assert response.status_code == 204

    folder.refresh_from_db()
    assert folder.deleted_at is not None


def test_api_items_restrict_children_list_excluded_user_has_no_role():
    """Listing children of a restricted folder does not leak ancestor roles."""
    excluded_user = factories.UserFactory()
    grandparent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(excluded_user, "owner")],
    )
    folder = factories.ItemFactory(
        parent=grandparent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
    )
    owner = factories.UserFactory()
    factories.UserItemAccessFactory(item=folder, user=owner, role="owner")
    factories.UserItemAccessFactory(item=folder, user=excluded_user, role="reader")
    factories.ItemFactory(parent=folder, type=models.ItemTypeChoices.FOLDER)

    client = APIClient()
    client.force_login(excluded_user)

    response = client.get(f"/api/v1.0/items/{folder.id!s}/children/")
    assert response.status_code == 200

    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["user_role"] == "reader"
