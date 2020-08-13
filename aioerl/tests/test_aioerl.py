from aioerl import current_proc
from aioerl import receive
from aioerl import reply
from aioerl import send
from aioerl import spawn
from aioerl import spawn_link

import asyncio
import pytest


@pytest.mark.asyncio
async def test_ping_pong():
    async def ping_pong():
        while True:
            m = await receive()
            if m.is_ok and m.body == "ping":
                await reply("pong")
            else:
                raise Exception("Invalid message body")

    p = await spawn(ping_pong())

    await send(p, "ping")
    m = await receive()
    assert m.is_ok and m.body == "pong"

    await send(p, "pang")
    m = await receive()
    assert m.is_err and isinstance(m.body, Exception)


@pytest.mark.asyncio
async def test_timeout():
    async def ping_pong_unresponsive():
        await asyncio.sleep(100)

    p = await spawn(ping_pong_unresponsive())
    await send(p, "ping")
    msg = await receive(timeout=0.1)
    assert msg.is_timeout


@pytest.mark.asyncio
async def test_process_crashes():
    async def process_crashed():
        await receive()
        raise Exception("i'm dead")

    p = await spawn(process_crashed())
    await send(p, "ping")

    m = await receive()
    assert m.is_err
    assert m.sender == p
    assert isinstance(m.body, Exception)
    assert str(m.body) == "i'm dead"


@pytest.mark.asyncio
async def test_fetch():
    async def fetch():
        m = await receive(timeout=10)
        if m.is_ok:
            url = m.body
            response = f"This is the content fo {url}"
            await reply((url, response))

    urls = ["http://erlang.org", "https://python.org/", "https://gitlab.com"]
    for url in urls:
        p = await spawn(fetch())
        await send(p, url)

    results = {}
    while True:
        m = await receive(timeout=0.1)
        if m.is_ok:
            url, response = m.body
            results[url] = response
        elif m.is_timeout:
            break
    assert set(results.keys()) == set(urls)


@pytest.mark.asyncio
async def test_noproc():
    async def dummy():
        await receive()  # waiting for a message before terminate

    p = await spawn(dummy())

    await send(p, "hey you!")
    m = await receive()
    assert m.is_exit
    assert m.sender == p
    assert m.body == "normal"

    await send(p, "hey you!")
    m = await receive()
    assert m.is_exit
    assert m.sender == p
    assert m.body == "noproc"


@pytest.mark.asyncio
async def test_task_cancelled():
    async def dummy():
        await asyncio.sleep(1)

    p = await spawn(dummy())
    assert p.kill() == True

    m = await receive()
    assert m.is_exit
    assert m.sender == p
    assert m.body == "killed"


@pytest.mark.asyncio
async def test_process_link():
    async def dummy():
        await asyncio.sleep(0.1)

    await spawn_link(dummy())
    m = await receive()
    assert m.is_exit
    assert m.body == "normal"


@pytest.mark.asyncio
async def test_process_link_crashes():
    async def dummy():
        await asyncio.sleep(0.1)
        raise Exception("bye")

    child = await spawn_link(dummy())
    parent = current_proc()
    assert parent.link is child
    m = await receive()
    assert m.is_err
    assert str(m.body) == "bye"
    assert parent.link is None


@pytest.mark.asyncio
async def test_multiple_childs():
    async def multi(n):
        while m := await receive():
            if m.body == "finish":
                break
            await reply(m.body * n)

    for i in range(3):
        await spawn(multi(1 + i))

    parent = current_proc()
    for child in parent.children:
        await send(child, 1)

    results = {
        m.body
        for _ in range(len(parent.children))
        for m in [await receive()]
        if m.is_ok
    }
    assert results == {1, 2, 3}

    for child in parent.children:
        await send(child, "finish")

    await asyncio.sleep(0.1)  # wait until finish
    assert parent.children == []
