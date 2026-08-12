import asyncio
from src.loats.utils.rate_limiter import get_order_rate_limiter, _reset_singletons_for_testing

_reset_singletons_for_testing()
lim = get_order_rate_limiter()

async def run():
    results = []
    for i in range(55):
        r = await lim.acquire()
        results.append(r)
    print(results)

asyncio.run(run())
