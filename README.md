# aioerl

[![PyPI version](https://badge.fury.io/py/aioerl.svg)](https://badge.fury.io/py/aioerl)

`aioerl` is a python library that mimics the philosophy of Erlang's processes with asyncio tasks.

Implements the following ideas:

- **Each process has a mailbox**: a queue to receive messages from other processes.
- **Message passing**: processes communicate entirely with messages (from the point of view of the developer)
- **Supervisor/monitors**: processes can monitor other processes (when a process dies or crashes, sends a message to its supervisor with the exit reason or the exception)

## Why?

`asyncio` is awesome and built-in structures like `asyncio.Queue` are great for communicating between tasks but is hard to manage errors.

With `aioerl`, a process just waits for incoming messages from other processes and decides what to do for each event (see [example](##example)).

## Quickstart

Requirements: Python 3.7+

Installation:

```bash
pip install aioerl
```

## Example

```python
from aioerl import spawn_monitored, receive, reply, send, run

async def ping_pong():
    while True:
        m = await receive(timeout=10)
        if m.is_ok:
            if m.body == "ping":
                await reply("pong")
            else:
                raise Exception("Invalid message body")
        elif m.is_timeout:
            return  # terminate process


async def main():
    p = await spawn_monitored(ping_pong())

    await send(p, "ping")
    print(await receive())  # Message(sender=<ErlProc:2>, event='ok', body='pong')

    await send(p, "pang")
    print(await receive())  # Message(sender=<ErlProc:2>, event='err', body=Exception("Invalid message body"))

    await send(p, "ping")
    print(await receive())  # Message(sender=<ErlProc:2>, event='exit', body='noproc')


if __name__ == "__main__":
    run(main())
```

## TODO:

Lot of things!