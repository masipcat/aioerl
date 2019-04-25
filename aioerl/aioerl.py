import asyncio
import re
from dataclasses import dataclass
from typing import Any
from typing import Tuple

import async_timeout


@dataclass
class Message:
    sender: "ErlProcess"
    event: str
    body: Any

    @property
    def is_ok(self):
        return self.event == "ok"

    @property
    def is_timeout(self):
        return self.event == "timeout"

    @property
    def is_exit(self):
        return self.event == "exit"

    @property
    def is_err(self):
        return self.event == "err"


class ErlProcess(asyncio.Task):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.link = None
        self.mailbox = asyncio.Queue()
        self.current_msg = None
        self.is_alive = True

    def __repr__(self):
        if self.link:
            return f"<ErlProc:{id(self)} linked:{id(self.link)}>"
        return f"<ErlProc:{id(self)}>"

    async def _send(self, internal_event, msg, from_process=None):
        if from_process is None:
            from_process = asyncio.current_task()

        if self.is_alive:
            return await self.mailbox.put((from_process, (internal_event, msg)))
        else:
            # Trying to send a message to a dead process -> replies to the sender with ("exit", "noproc")
            return await this_process()._send("exit", "noproc", from_process=self)

    def _send_nowait(self, internal_event, msg, from_process=None):
        if from_process is None:
            from_process = asyncio.current_task()
        return self.mailbox.put_nowait((from_process, (internal_event, msg)))

    async def _receive(self, timeout=None):
        try:
            self.current_msg = None
            with async_timeout.timeout(timeout):
                msg = await self.mailbox.get()
            self.current_msg = msg
        except asyncio.TimeoutError:
            self.current_msg = (this_process(), ("timeout", None))
        return self.current_msg

    def kill(self):
        return self.cancel()


def process_factory(loop, coro):
    process = ErlProcess(coro, loop=loop)
    if process._source_traceback:
        del process._source_traceback[-1]
    return process


def this_process():
    return asyncio.current_task()


def _get_raw(process=None) -> Tuple["ErlProcess", Tuple[str, Any]]:
    process = process or this_process()
    msg = process.current_msg
    if not msg:
        raise Exception("Message not received")
    return msg


def get(process=None) -> Message:
    proc, (event, body) = _get_raw(process=process)
    return Message(proc, event, body)


async def receive(timeout=None, process=None) -> Message:
    process = process or this_process()
    proc, (event, body) = await process._receive(timeout)
    return Message(proc, event, body)


async def receive_or_fail(
    wait_for_events, ignore_events=None, sender=None, timeout=None, process=None, **kwargs
):
    if isinstance(wait_for_events, str):
        wait_for_events = (wait_for_events,)
    ignore_events = ignore_events or tuple()
    check_body = "body" in kwargs

    def _fail(m):
        if m.is_exit:
            raise Exception(str(m))
        elif m.is_timeout:
            raise asyncio.TimeoutError()
        elif m.is_err:
            raise m.body
        else:
            raise Exception(str(m))

    m = await receive(timeout=timeout, process=process)
    if m.event not in wait_for_events and m.event not in ignore_events:
        _fail(m)
    if check_body and m.body != kwargs["body"]:
        _fail(m)
    if sender and m.sender != sender:
        _fail(m)
    return m


async def send(dest_process, msg):
    return await dest_process._send("ok", msg)


async def reply(body: Any):
    m = get()
    return await send(m.sender, body)


def clear_mailbox():
    process = this_process()
    while not process.mailbox.empty():
        process.mailbox.get_nowait()


async def spawn_link(coro, trap=True):
    if trap is False:
        raise NotImplementedError("Trap = False not implemented")
    process = this_process()
    if process.link is not None:
        raise Exception(f"This process already linked to process {process.link}")
    future = asyncio.create_task(_link(coro, process))
    future.add_done_callback(lambda fut: callback(fut, process))
    process.link = future
    return future


async def spawn_monitored(coro):
    process = this_process()
    future = asyncio.create_task(_monitor(coro, process))
    future.add_done_callback(lambda fut: callback(fut, process))
    return future


async def _link(coro, process):
    this_process().link = process
    await _monitor(coro, process)
    this_process().link = None
    process.link = None


async def _monitor(coro, process):
    await coro
    clear_mailbox()


def callback(fut, process):
    try:
        fut.result()
    except asyncio.CancelledError as e:
        fut.is_alive = False
        process._send_nowait("exit", "killed", from_process=fut)
        raise
    except Exception as e:
        fut.is_alive = False
        process._send_nowait("err", e, from_process=fut)
    else:
        fut.is_alive = False
        process._send_nowait("exit", "normal", from_process=fut)


def run(coro):
    loop = asyncio.get_event_loop()
    loop.set_task_factory(process_factory)
    loop.run_until_complete(coro)
    loop.close()
