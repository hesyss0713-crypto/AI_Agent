# core/bridge_client.py
import asyncio, json, logging, threading
import websockets
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

BRIDGE_PING_INTERVAL = 20
BRIDGE_PING_TIMEOUT = 20
BRIDGE_RECONNECT_MAX_BACKOFF = 10

class BridgeClient:
    def __init__(self, url: str, on_incoming: callable):
        self.url = url
        self.on_incoming = on_incoming
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._stop = threading.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._manager_task: Optional[asyncio.Task] = None
        self._out_q: "asyncio.Queue[str]" = asyncio.Queue(maxsize=1000)

    def start(self):
        if self._loop is not None:
            return
        t = threading.Thread(target=self._run_loop, name="BridgeClientLoop", daemon=True)
        t.start()

    def stop(self):
        self._stop.set()
        if self._loop and self._manager_task:
            asyncio.run_coroutine_threadsafe(self._cancel_task(self._manager_task), self._loop)

    def send(self, message: Dict[str, Any] | str):
        payload = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._out_q.put(payload), self._loop)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._manager_task = self._loop.create_task(self._manager())
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop=self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    async def _manager(self):
        backoff = 1
        while not self._stop.is_set():
            try:
                logger.info("[Bridge] connecting to %s", self.url)
                async with websockets.connect(
                    self.url,
                    ping_interval=BRIDGE_PING_INTERVAL,
                    ping_timeout=BRIDGE_PING_TIMEOUT,
                    max_queue=None,
                ) as ws:
                    self.ws = ws
                    logger.info("[Bridge] connected")

                    await self._safe_send("Supervisor is connected")

                    reader = asyncio.create_task(self._reader_loop())
                    writer = asyncio.create_task(self._writer_loop())

                    done, pending = await asyncio.wait(
                        {reader, writer}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
            except Exception as e:
                logger.warning("[Bridge] disconnected: %s", e)
            finally:
                self.ws = None
                if self._stop.is_set():
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BRIDGE_RECONNECT_MAX_BACKOFF)

    async def _reader_loop(self):
        assert self.ws is not None
        async for raw in self.ws:
            try:
                data = json.loads(raw)
            except Exception:
                data = {"type": "raw", "text": raw}
            try:
                self.on_incoming(data)
            except Exception as e:
                logger.exception("[Bridge] on_incoming error: %s", e)

    async def _writer_loop(self):
        assert self.ws is not None
        while True:
            payload: str = await self._out_q.get()
            try:
                await self.ws.send(payload)
            except Exception as e:
                logger.warning("[Bridge] send failed: %s", e)
                break

    async def _safe_send(self, obj: Dict[str, Any]):
        if self.ws and getattr(self.ws, "closed", False) is False:
            await self.ws.send(json.dumps(obj, ensure_ascii=False))

    async def _cancel_task(self, t: Optional[asyncio.Task]):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass
