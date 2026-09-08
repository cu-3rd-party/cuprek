"""``IdRegistry`` behaviour, exercised against a real database.

Reuses the ``sessionmaker`` fixture from ``test_repo`` (same drop/create-per-test
isolation), so these skip together with the other DB tests when no database is
configured.
"""
from __future__ import annotations

from circlebot.services.access import ADMIN, GUARANTEED, IdRegistry

from .test_repo import sessionmaker  # noqa: F401  (pytest fixture)


def test_roots_are_effective_without_a_database() -> None:
    reg = IdRegistry(root_admins=frozenset({1, 2}), root_guaranteed=frozenset({9}))
    assert reg.is_admin(1) and reg.is_admin(2)
    assert not reg.is_admin(3)
    assert reg.is_guaranteed(9)
    assert not reg.is_guaranteed(1)  # the two lists are independent


def test_none_user_id_is_never_privileged() -> None:
    # message.from_user can be None; the guard must not crash or grant access.
    reg = IdRegistry(root_admins=frozenset({1}))
    assert not reg.is_admin(None)
    assert not reg.is_guaranteed(None)


async def test_add_then_remove_roundtrip(sessionmaker) -> None:  # noqa: F811
    reg = IdRegistry(root_admins=frozenset({1}))
    async with sessionmaker() as session:
        assert await reg.add(session, ADMIN, 42, added_by=1) is True
        await session.commit()

    assert reg.is_admin(42)
    assert reg.managed(ADMIN) == {42}
    assert reg.effective(ADMIN) == {1, 42}

    async with sessionmaker() as session:
        assert await reg.remove(session, ADMIN, 42) is True
        await session.commit()

    assert not reg.is_admin(42)
    assert reg.managed(ADMIN) == set()


async def test_add_is_idempotent(sessionmaker) -> None:  # noqa: F811
    reg = IdRegistry()
    async with sessionmaker() as session:
        assert await reg.add(session, ADMIN, 7, added_by=None) is True
        assert await reg.add(session, ADMIN, 7, added_by=None) is False
        await session.commit()
    assert reg.managed(ADMIN) == {7}


async def test_adding_an_existing_root_is_a_no_op(sessionmaker) -> None:  # noqa: F811
    """A root is already in effect, so storing it again would be dead weight."""
    reg = IdRegistry(root_admins=frozenset({5}))
    async with sessionmaker() as session:
        assert await reg.add(session, ADMIN, 5, added_by=None) is False
        await session.commit()
    assert reg.managed(ADMIN) == set()
    assert reg.is_admin(5)


async def test_roots_cannot_be_removed(sessionmaker) -> None:  # noqa: F811
    """The lockout guard: .env admins survive any /admins rm."""
    reg = IdRegistry(root_admins=frozenset({1, 2}))
    async with sessionmaker() as session:
        assert await reg.remove(session, ADMIN, 1) is False
        await session.commit()
    assert reg.is_admin(1)
    assert reg.is_root(ADMIN, 1)
    assert not reg.is_root(ADMIN, 99)


async def test_removing_an_absent_id_reports_false(sessionmaker) -> None:  # noqa: F811
    reg = IdRegistry()
    async with sessionmaker() as session:
        assert await reg.remove(session, ADMIN, 12345) is False
        await session.commit()


async def test_load_restores_state_across_restart(sessionmaker) -> None:  # noqa: F811
    """The whole point of the feature: added IDs outlive the process."""
    async with sessionmaker() as session:
        first = IdRegistry(root_admins=frozenset({1}))
        await first.add(session, ADMIN, 42, added_by=1)
        await first.add(session, GUARANTEED, 77, added_by=1)
        await session.commit()

    # A fresh registry, as if the container had just restarted.
    second = IdRegistry(root_admins=frozenset({1}))
    async with sessionmaker() as session:
        await second.load(session)

    assert second.is_admin(42)
    assert second.is_guaranteed(77)
    assert second.effective(ADMIN) == {1, 42}
    assert not second.is_admin(77)  # kinds stay separate through a reload


async def test_kinds_are_independent(sessionmaker) -> None:  # noqa: F811
    reg = IdRegistry()
    async with sessionmaker() as session:
        await reg.add(session, ADMIN, 100, added_by=None)
        await reg.add(session, GUARANTEED, 100, added_by=None)
        await session.commit()
        # Same id in both lists is legitimate and removing one leaves the other.
        assert await reg.remove(session, ADMIN, 100) is True
        await session.commit()

    assert not reg.is_admin(100)
    assert reg.is_guaranteed(100)
