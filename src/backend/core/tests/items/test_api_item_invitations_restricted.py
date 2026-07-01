"""
Tests for item invitations API endpoints on restricted folders.
"""

import pytest
from rest_framework.test import APIClient

from core import factories, models

pytestmark = pytest.mark.django_db


def test_api_item_invitations_delete_restricted_ancestor_owner():
    """An ancestor owner without access to a restricted folder cannot cancel its invitations."""
    ancestor_owner = factories.UserFactory()
    folder_owner = factories.UserFactory()
    parent = factories.ItemFactory(
        type=models.ItemTypeChoices.FOLDER,
        users=[(ancestor_owner, models.RoleChoices.OWNER)],
    )
    folder = factories.ItemFactory(
        parent=parent,
        type=models.ItemTypeChoices.FOLDER,
        is_restricted=True,
        users=[(folder_owner, models.RoleChoices.OWNER)],
    )
    invitation = factories.InvitationFactory(item=folder)

    client = APIClient()
    client.force_login(ancestor_owner)

    response = client.delete(
        f"/api/v1.0/items/{folder.id!s}/invitations/{invitation.id!s}/",
    )
    assert response.status_code == 403
    assert models.Invitation.objects.filter(id=invitation.id).exists()
