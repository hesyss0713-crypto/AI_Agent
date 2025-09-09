from core.bridge_client import BridgeClient

def register_bridge_handler(supervisor, bridge_url="ws://172.17.0.5:9013/ws/supervisor"):

    type_action_map = {
        "chat": "user_input_normal",
        "user_input": "user_input_normal",
        "pending_response": "user_input_pending",
        "reset": "reset",
    }

    supervisor.bridge = BridgeClient(bridge_url, on_incoming=supervisor._on_bridge_message)
    supervisor.bridge.start()
