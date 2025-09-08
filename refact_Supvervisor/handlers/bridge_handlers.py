from core.bridge_client import BridgeClient

def register_bridge_handler(supervisor, bridge_url="ws://172.17.0.5:9013/ws/supervisor"):

    type_action_map = {
        "chat": "user_input_normal",
        "user_input": "user_input_normal",
        "pending_response": "user_input_pending",
        "reset": "reset",
    }

    def on_bridge_message(msg: dict):
        supervisor.logger.info(f"[Bridge] incoming: {msg}")

        text = msg.get("text", "")
        mtype = msg.get("type", "user_input")

        # 매핑 적용
        action = type_action_map.get(mtype, "user_input_normal")

        event_msg = {
            "command": None,
            "action": action,
            "text": text,
            "cid": msg.get("cid"),
            "pending": msg.get("pending"),  # pending 응답이 있으면 같이 넘김
        }

        # Supervisor 이벤트로 전달
        supervisor.emitter.emit("user_message", event_msg)

    supervisor.bridge = BridgeClient(bridge_url, on_incoming=on_bridge_message)
    supervisor.bridge.start()
