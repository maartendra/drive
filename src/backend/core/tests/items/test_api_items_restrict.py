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
