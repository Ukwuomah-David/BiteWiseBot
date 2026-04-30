import asyncio

EVENT_QUEUE = asyncio.Queue()

async def emit(event: dict):
    await EVENT_QUEUE.put(event)


async def consume():
    while True:
        event = await EVENT_QUEUE.get()
        await dispatch(event)