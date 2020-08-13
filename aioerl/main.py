from .utils import task_name
from contextvars import ContextVar
from copy import copy
from dataclasses import dataclass
from typing import Any
from typing import Optional
from typing import Tuple

import asyncio
import logging
import weakref

logger = logging.getLogger("aioerl")

_current_proc = ContextVar("current_proc")


@dataclass
class Message:
    sender: "Process"
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


class Process:
    def __init__(self, parent: Optional["Process"]) -> None:
        self._task = None
        self._parent = parent
        self._children = []

        if parent:
            parent._children += [self]

        self.link = None
        self.mailbox = asyncio.Queue()
        self.current_msg = None
        self.is_alive = True

    def __repr__(self):
        if self.link:
            return f"<Proc:{task_name(self.task)} linked:{task_name(self.link.task)}>"
        return f"<Proc:{task_name(self.task)}>"

    def set_task(self, task):
        self._task = weakref.ref(task)
        task.add_done_callback(self._task_callback)

    @property
    def task(self):
        if self._task:
            return self._task()
        return None

    @property
    def children(self):
        return copy(self._children)

    def _task_callback(self, task):
        assert task == self._task()
        try:
            task.result()
        except asyncio.CancelledError as e:
            if self._parent:
                self._parent._append_mailbox_nowait("exit", "killed", sender=self)
            raise
        except Exception as e:
            if self._parent:
                self._parent._append_mailbox_nowait("err", e, sender=self)
        else:
            if self._parent:
                self._parent._append_mailbox_nowait("exit", "normal", sender=self)
        finally:
            self.is_alive = False
            if self._parent:
                self._parent._children.remove(self)
            self._parent = None
            self.mailbox = None
            self.link = None

    async def _append_mailbox(
        self, internal_event: str, msg, sender: Optional["Process"] = None
    ):
        if sender is None:
            sender = current_proc()

        if self.is_alive:
            data = (internal_event, msg)
            logger.debug(f"{sender} -> {self}: {data}")
            return await self.mailbox.put((sender, data))
        else:
            # Trying to send a message to a dead process -> replies to the sender with ("exit", "noproc")
            return await current_proc()._append_mailbox("exit", "noproc", sender=self)

    def _append_mailbox_nowait(
        self, internal_event: str, msg, sender: Optional["Process"] = None
    ):
        if sender is None:
            sender = current_proc()
        data = (internal_event, msg)
        logger.debug(f"{sender} -> {self}: {data}")
        return self.mailbox.put_nowait((sender, data))

    async def _receive(self, timeout=None):
        if timeout == 0:
            raise RuntimeError("Timeout must be greater than zero or None")

        self.current_msg = None
        try:
            self.current_msg = await asyncio.wait_for(self.mailbox.get(), timeout)
        except asyncio.TimeoutError:
            self.current_msg = (current_proc(), ("timeout", None))
        return self.current_msg

    def kill(self):
        if self.task:
            return self.task.cancel()
        return False


def current_proc(*, create=False) -> Process:
    try:
        return _current_proc.get()
    except LookupError:
        if create:
            proc = Process(None)
            _current_proc.set(proc)
            proc.set_task(asyncio.current_task())
            return proc
        else:
            raise


def _get_raw(process=None) -> Tuple["Process", Tuple[str, Any]]:
    process = process or current_proc()
    msg = process.current_msg
    if not msg:
        raise Exception("Message not received")
    return msg


def get(process=None) -> Message:
    proc, (event, body) = _get_raw(process=process)
    return Message(proc, event, body)


async def receive(timeout=None, process=None) -> Message:
    process = process or current_proc()
    proc, (event, body) = await process._receive(timeout)
    return Message(proc, event, body)


async def receive_or_fail(
    wait_for_events,
    ignore_events=None,
    sender=None,
    timeout=None,
    process=None,
    **kwargs,
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
    elif check_body and m.body != kwargs["body"]:
        _fail(m)
    elif sender and m.sender != sender:
        _fail(m)
    else:
        return m


async def send(dest_proc: Process, msg):
    return await dest_proc._append_mailbox("ok", msg)


async def reply(body: Any):
    m = get()
    return await send(m.sender, body)


def clear_mailbox():
    mailbox = current_proc().mailbox
    while not mailbox.empty():
        mailbox.get_nowait()


async def spawn(coro) -> Process:
    parent = current_proc(create=True)
    child = Process(parent)
    task = asyncio.create_task(_prepare_child(child, coro))
    child.set_task(task)
    return child


async def spawn_link(coro, trap=True) -> Process:
    if trap is False:
        raise NotImplementedError("Trap = False not implemented")
    parent = current_proc(create=True)
    if parent.link is not None:
        raise Exception(f"This process already linked to process {parent.link}")
    child = Process(parent)
    parent.link = child
    task = asyncio.create_task(_prepare_child(child, _link(coro, parent)))
    child.set_task(task)
    return child


async def _prepare_child(child, coro):
    _current_proc.set(child)
    logger.debug(f"{child._parent} spawn-> {child}")
    val = await coro
    return val


async def _link(coro, parent):
    this_proc = current_proc()
    this_proc.link = parent
    try:
        res = await coro
    finally:
        this_proc.link = None
        parent.link = None
    return res
