from app.repositories.memberships import InMemoryMembershipRepository


def test_membership_repository_resolves_user_tenant_identity() -> None:
    repository = InMemoryMembershipRepository(
        memberships={7: 10, 8: 20},
    )

    identity = repository.get_identity_for_user(7)

    assert identity is not None
    assert identity.user_id == 7
    assert identity.tenant_id == 10


def test_membership_repository_returns_none_for_unknown_user() -> None:
    repository = InMemoryMembershipRepository(memberships={7: 10})

    assert repository.get_identity_for_user(999) is None
