import asyncio
from collections.abc import Awaitable, Callable

type TaskBlock = Callable[[], Awaitable[None]]


class Throttler:
    """Trailing-edge throttler.

    Schedules at most one pending run and executes it after the configured
    interval. Repeated `call()` invocations while a run is already pending are
    ignored.
    """

    def __init__(
        self,
        rate_limit: int,
        period: int | float = 1.0,
    ):
        if rate_limit <= 0:
            msg = "rate_limit must be greater than 0"
            raise ValueError(msg)
        if period <= 0:
            msg = "period must be greater than 0"
            raise ValueError(msg)

        #
        self._rate_limit = float(rate_limit)
        self._period = float(period)
        self._interval = self._period / self._rate_limit

        #
        self._next_task_block_lock = asyncio.Lock()
        self._next_task_block: TaskBlock | None = None

        #
        self._last_run_task_time: float | None = None
        self._next_handle: asyncio.TimerHandle | None = None

    async def call(self, task_block: TaskBlock) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()

        async with self._next_task_block_lock:
            self._next_task_block = task_block

        if self._next_handle:
            return

        if self._last_run_task_time and now < self._last_run_task_time + self._interval:
            _pending_task_time = self._last_run_task_time + self._interval
        else:
            _pending_task_time = now + 0.01

        next_interval = max(0, _pending_task_time - now)
        self._next_handle = loop.call_later(next_interval, self._run_task)

    async def flush(self) -> None:
        if not self._next_handle:
            return

        self._next_handle.cancel()
        await self._run_task_async()

    def _run_task(self) -> None:
        asyncio.create_task(self._run_task_async())

    async def _run_task_async(self) -> None:
        async with self._next_task_block_lock:
            task_block = self._next_task_block
            self._next_task_block = None

        try:
            if task_block:
                await task_block()
        finally:
            self._last_run_task_time = asyncio.get_running_loop().time()
            self._next_handle = None
