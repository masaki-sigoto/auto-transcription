import asyncio
from typing import Optional, Callable, Any
from concurrent.futures import ThreadPoolExecutor
import functools


# スレッドプールエグゼキューター
_thread_pool: Optional[ThreadPoolExecutor] = None


def get_thread_pool(max_workers: int = 4) -> ThreadPoolExecutor:
    """スレッドプールを取得"""
    global _thread_pool
    if _thread_pool is None:
        _thread_pool = ThreadPoolExecutor(max_workers=max_workers)
    return _thread_pool


async def run_in_thread(func: Callable, *args, **kwargs) -> Any:
    """同期関数をスレッドプールで実行"""
    loop = asyncio.get_event_loop()
    executor = get_thread_pool()
    return await loop.run_in_executor(
        executor,
        functools.partial(func, *args, **kwargs)
    )


def background_task(func: Callable):
    """バックグラウンドタスクデコレーター"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        asyncio.create_task(func(*args, **kwargs))
    return wrapper


class BatchProcessor:
    """バッチ処理ヘルパー"""

    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size

    async def process(
        self,
        items: list,
        processor: Callable,
        concurrency: int = 5,
    ) -> list:
        """アイテムをバッチ処理"""
        results = []

        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]

            # 同時実行数を制限
            semaphore = asyncio.Semaphore(concurrency)

            async def process_with_semaphore(item):
                async with semaphore:
                    return await processor(item)

            batch_results = await asyncio.gather(
                *[process_with_semaphore(item) for item in batch]
            )
            results.extend(batch_results)

        return results


class ConnectionPool:
    """接続プール管理"""

    def __init__(self, max_connections: int = 10):
        self.max_connections = max_connections
        self._semaphore = asyncio.Semaphore(max_connections)
        self._connections: list = []

    async def acquire(self) -> Any:
        """接続を取得"""
        async with self._semaphore:
            if self._connections:
                return self._connections.pop()
            return await self._create_connection()

    async def release(self, connection: Any):
        """接続を解放"""
        self._connections.append(connection)

    async def _create_connection(self) -> Any:
        """新しい接続を作成（サブクラスでオーバーライド）"""
        raise NotImplementedError

    async def close_all(self):
        """全接続を閉じる"""
        for conn in self._connections:
            await self._close_connection(conn)
        self._connections.clear()

    async def _close_connection(self, connection: Any):
        """接続を閉じる（サブクラスでオーバーライド）"""
        raise NotImplementedError


class LazyLoader:
    """遅延ローディングヘルパー"""

    def __init__(self, loader: Callable):
        self._loader = loader
        self._value = None
        self._loaded = False
        self._lock = asyncio.Lock()

    async def get(self) -> Any:
        """値を取得（必要な時のみロード）"""
        if self._loaded:
            return self._value

        async with self._lock:
            if not self._loaded:
                self._value = await self._loader()
                self._loaded = True

        return self._value

    def reset(self):
        """リセット"""
        self._value = None
        self._loaded = False


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    """リストをチャンクに分割"""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def gather_with_limit(
    tasks: list,
    limit: int = 10,
    return_exceptions: bool = False,
) -> list:
    """同時実行数を制限したgather"""
    semaphore = asyncio.Semaphore(limit)

    async def limited_task(task):
        async with semaphore:
            return await task

    return await asyncio.gather(
        *[limited_task(task) for task in tasks],
        return_exceptions=return_exceptions,
    )
