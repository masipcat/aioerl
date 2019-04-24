from aioerl import process_factory

import asyncio
import pytest


@pytest.fixture()
def event_loop():
    loop = asyncio.new_event_loop()
    loop.set_task_factory(process_factory)
    yield loop
    loop.close()
