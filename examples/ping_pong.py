from aioerl import receive
from aioerl import reply
from aioerl import send
from aioerl import spawn

import asyncio


async def ping_pong():
    while m := await receive(timeout=10):
        if m.is_ok:
            if m.body == "ping":
                await reply("pong")
            else:
                raise Exception("Invalid message body")
        elif m.is_timeout:
            return  # terminate process


async def main():
    p = await spawn(ping_pong())

    await send(p, "ping")
    print(await receive())  # Message(sender=<Proc:Task-2>, event='ok', body='pong')

    await send(p, "pang")
    print(await receive())  # Message(sender=<Proc:Task-2>, event='err', body=Exception('Invalid message body'))

    await send(p, "ping")
    print(await receive())  # Message(sender=<Proc:Task-2>, event='exit', body='noproc')


if __name__ == "__main__":
    asyncio.run(main())
