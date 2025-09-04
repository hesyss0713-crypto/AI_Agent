# supervisor.py
import logging
import yaml
import json
import time
import threading
import asyncio
from pathlib import Path
from queue import Queue, Empty
from typing import Optional, Dict, Any

import websockets  # pip install websockets (!!! websocket-client 아님)

from utils.network import supervisor_socket, event_emitter
from utils.db.db import DBManager  # 유지
from utils.router import CommandRouter
from utils.intent import IntentClassifier
from utils.message_builder import build_task, build_response
from handlers.git_handler import GitHandler
from llm.llm_manager import LLMManager

BASE_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---- 브릿지(9013) WebSocket 설정 ----
BRIDGE_WS_URL = "ws://192.168.104.27:9013/ws/supervisor"
BRIDGE_PING_INTERVAL = 20
BRIDGE_PING_TIMEOUT = 20
BRIDGE_RECONNECT_MAX_BACKOFF = 10


class BridgeClient:
    """
    Supervisor → FastAPI(9013) 브릿지와 영속적으로 연결하는 클라이언트.
    """
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

                    await self._safe_send({"type": "system", "text": "supervisor_connected(9013)"})

                    reader = asyncio.create_task(self._reader_loop())
                    writer = asyncio.create_task(self._writer_loop())

                    done, pending = await asyncio.wait(
                        {reader, writer}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for t in pending:
                        t.cancel()
            except Exception as e:
                logger.warning("[Bridge] disconnected: %s", e)
                try:
                    await self._safe_broadcast_local(
                        {"type": "system", "text": f"supervisor_disconnected(9013): {e}"}
                    )
                except Exception:
                    pass
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
                break  # 연결이 끊기면 루프 종료

    async def _safe_send(self, obj: Dict[str, Any]):
        if self.ws and getattr(self.ws, "closed", False) is False:
            await self.ws.send(json.dumps(obj, ensure_ascii=False))

    async def _safe_broadcast_local(self, obj: Dict[str, Any]):
        _ = obj  # hook 자리

    async def _cancel_task(self, t: Optional[asyncio.Task]):
        if t and not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


class Supervisor:
    def __init__(self, model_name: str, host: str, port: int):
        self.llm = LLMManager(model_name)
        self.socket = supervisor_socket.SupervisorServer(host, port)

        self.prompts = self.load_prompts()
        self.router = CommandRouter(self.llm, self.prompts)
        self.intent_cls = IntentClassifier(self.llm, self.prompts)
        self.git_handler = GitHandler(self.llm, self.prompts)

        self.emitter = self.socket.emitter
        self.emitter.on("coder_message", self.on_coder_message)

        self.user_q: "Queue[str]" = Queue()

        self.bridge = BridgeClient(BRIDGE_WS_URL, on_incoming=self._on_bridge_message)
        self.bridge.start()

    def _on_bridge_message(self, msg: Dict[str, Any]):
        try:
            mtype = str(msg.get("type", "")).lower()
            text = str(msg.get("text", "")).strip()

            if mtype in ("user_input", "input", "prompt", "chat") and text:
                self.user_q.put(text)
                self._send_to_bridge({"type": "user_input(received)", "text": text})
                return

            if mtype == "reset":
                self.llm.reset_memory()
                self._send_to_bridge({"type": "system", "text": "LLM memory reset"})
                return

            self._send_to_bridge({"type": "supervisor_log", "text": f"ignored message: {msg}"})
        except Exception as e:
            logger.exception("[Supervisor] _on_bridge_message error: %s", e)
            self._send_to_bridge({"type": "error", "text": f"_on_bridge_message: {e}"})

    def _send_to_bridge(self, message: Dict[str, Any] | str):
        self.bridge.send(message)

    def load_prompts(self, path=BASE_DIR / "config" / "prompts.yaml") -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def on_coder_message(self, msg: dict):
        print("[Supervisor] 이벤트 수신:", msg)
        self._send_to_bridge({"type": "coder_event", **msg})

        if msg.get("command") == "git":
            if msg.get("action") == "edit":
                metadata = msg.get("metadata", {})
                print("\n[Supervisor] Coder가 제안한 코드 수정안:")
                for filename, content in metadata.items():
                    print(f"\n--- {filename} ---\n{content}\n")

                self._send_to_bridge({
                    "type": "pending",
                    "text": "이 수정 내용으로 학습을 진행할까요? (yes/no/revise)"
                })
                user_input = self._wait_user_text()

                intent = self.intent_cls.get_intent(user_input)

                if intent == "positive":
                    print("[Supervisor] 수정안을 토대로 학습을 진행하겠습니다.")
                    self._send_to_bridge({"type": "llm_output", "text": "수정안을 승인했습니다."})
                    task = build_task(command="git", action="run", target="train.py")
                    self.socket.send_supervisor_response(task)

                elif intent == "negative":
                    print("[Supervisor] 수정이 취소되었습니다.")
                    self._send_to_bridge({"type": "llm_output", "text": "수정이 취소되었습니다."})
                    raise StopIteration

                elif intent == "revise":
                    print("[Supervisor] 수정 재요청")
                    self._send_to_bridge({"type": "llm_output", "text": "수정안 재요청을 진행합니다."})

            elif msg.get("action") == "clone_repo":
                if msg.get("result") == "success":
                    print("[Supervisor] 환경 세팅 완료.")
                    task = build_task("git", "create_venv",
                                      metadata={"dir_path": "AI_Agent_Model/", "requirements": "requirements.txt"})
                    self.socket.send_supervisor_response(task)

            elif msg.get("action") == "read_py_files":
                model_summary = self.git_handler.summarize_experiment(msg, persistent=True)
                print(model_summary)
                self._send_to_bridge({"type": "model_summary", "text": model_summary})

    def _wait_user_text(self) -> str:
        while True:
            try:
                return self.user_q.get(timeout=0.1)
            except Empty:
                time.sleep(0.05)

    def run(self):
        self.llm.load_model()
        self.socket.run_main()  # 9006 WS 서버 (Agent용)

        self._send_to_bridge({"type": "system", "text": "supervisor_started"})

        while True:
            try:
                text = self._wait_user_text()

                if text.lower() == "exit":
                    print("[Supervisor] 종료")
                    self._send_to_bridge({"type": "system", "text": "supervisor_exiting"})
                    break

                if text.lower() == "reset":
                    self.llm.reset_memory()
                    print("[Supervisor] 대화 메모리 초기화됨.")
                    self._send_to_bridge({"type": "llm_output", "text": "대화 메모리를 초기화했습니다."})
                    continue

                command, persistent = self.router.get_command(text)
                self._send_to_bridge({
                    "type": "llm_output",
                    "text": f"요청을 분석했습니다. command={command}, persistent={persistent}"
                })

                task = build_task("git", "clone_repo",
                                  metadata={"git_url": "https://github.com/hesyss0713-crypto/AI_Agent_Model"})
                self.socket.send_supervisor_response(task)
                self._send_to_bridge({"type": "supervisor_cmd", "text": f"issued {task}"})

            except StopIteration:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.exception(e)
                self._send_to_bridge({"type": "error", "text": str(e)})


if __name__ == "__main__":
    model_name = "Qwen/Qwen2.5-1.5B-Instruct"
    host = "0.0.0.0"   # 9006 (Agent용)
    port = 9006
    supervisor = Supervisor(model_name, host, port)
    supervisor.run()
