import asyncio

from circlebot.services.locks import KeyedLock


async def test_same_key_is_serialised() -> None:
    locks = KeyedLock()
    order: list[str] = []

    async def worker(tag: str, hold: float) -> None:
        async with locks(("chat", 1)):
            order.append(f"{tag}-enter")
            await asyncio.sleep(hold)
            order.append(f"{tag}-exit")

    await asyncio.gather(worker("a", 0.05), worker("b", 0.0))

    # b must not enter before a has fully exited
    assert order == ["a-enter", "a-exit", "b-enter", "b-exit"]


async def test_different_keys_run_in_parallel() -> None:
    locks = KeyedLock()
    order: list[str] = []

    async def worker(key: object, tag: str) -> None:
        async with locks(key):
            order.append(f"{tag}-enter")
            await asyncio.sleep(0.05)
            order.append(f"{tag}-exit")

    await asyncio.gather(worker(("chat", 1), "a"), worker(("chat", 2), "b"))

    assert order[:2] == ["a-enter", "b-enter"] or order[:2] == ["b-enter", "a-enter"]


async def test_locks_are_released_and_pruned() -> None:
    locks = KeyedLock()
    async with locks("k"):
        pass
    assert locks._locks == {}
