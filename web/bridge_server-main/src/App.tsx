// src/App.tsx
import { useEffect, useRef, useState } from "react";

type Msg = {
  type: string;
  text?: string;
  data?: any;
  [k: string]: any;
};

export default function App() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const bottomRef = useRef<HTMLDivElement | null>(null);

  // 메시지가 추가될 때마다 자동으로 스크롤 맨 아래 이동
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // 1) WebSocket 연결 (브릿지 프록시 경유)
  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://localhost:9013/ws/client`);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);

    ws.onmessage = (ev) => {
      try {
        const msg: Msg = JSON.parse(ev.data);
        setMessages((prev) => [...prev, msg]);
      } catch {
        // ignore
      }
    };

    return () => ws.close();
  }, []);

  // 2) 사용자 입력을 REST(POST)로 전송 → 브릿지가 Supervisor에 포워드
  const sendByPost = async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");

    const res = await fetch("api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "user_input", text }),
    });
    await res.json().catch(() => ({}));

    setMessages((prev) => [...prev, { type: "user_post(local)", text }]);
  };

  return (
    <div className="h-screen w-screen flex items-center justify-center bg-gray-100">
      <div className="w-[90%] h-[90%] bg-white rounded-3xl shadow-2xl flex flex-col border border-gray-200 overflow-hidden">
        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 py-3 border-b bg-gray-50">
          <h1 className="text-xl font-semibold text-gray-800">Supervisor Bridge UI</h1>
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${
              connected ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
            }`}
          >
            {connected ? "🟢 WS Connected" : "🔴 WS Disconnected"}
          </span>
        </div>

        {/* 본문 */}
        <div className="flex-1 flex">
          {/* 왼쪽: 메시지 로그 */}
          <div className="w-2/3 flex flex-col bg-gray-50">
            <div className="p-3 border-b font-semibold">💬 Messages</div>
            <div className="flex-1 p-4 space-y-2 overflow-y-auto max-h-[600px]">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`p-3 rounded-2xl shadow-sm max-w-[85%] ${
                    (m.type || "").includes("user")
                      ? "bg-blue-100 text-blue-800 ml-auto"
                      : "bg-gray-100 text-gray-800"
                  }`}
                >
                  <div className="text-xs opacity-70 mb-1">{m.type}</div>
                  <div className="text-sm">{m.text ?? JSON.stringify(m.data ?? m)}</div>
                </div>
              ))}
              {/* 스크롤 자동 이동용 앵커 */}
              <div ref={bottomRef} />
            </div>
            <div className="p-3 border-t bg-white flex gap-2">
              <input
                className="flex-1 border rounded-2xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type message and POST to server…"
              />
              <button
                onClick={sendByPost}
                className="px-4 py-2 rounded-2xl bg-blue-600 text-white"
              >
                POST /api/send
              </button>
            </div>
          </div>

          {/* 오른쪽: 안내 */}
          <div className="w-1/3 p-4">
            <div className="text-sm text-gray-600">
              <p className="font-semibold mb-2">동작 개요</p>
              <ul className="list-disc ml-5 space-y-1">
                <li>입력은 <code>POST /api/send</code> 로 브릿지에 전달</li>
                <li>브릿지가 Supervisor(WS)로 포워드</li>
                <li>Supervisor 결과를 브릿지가 <code>/ws/client</code>로 push</li>
              </ul>
              <p className="mt-2 text-xs text-gray-500">
                * 운영(HTTPS)이면 자동으로 <code>wss://</code>로 연결됩니다.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
