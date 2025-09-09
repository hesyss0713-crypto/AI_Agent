import logging
from core.supervisor_base import Supervisor
from handlers.user_handlers import register_user_handlers
from handlers.git_handlers import register_git_handlers
from handlers.bridge_handlers import register_bridge_handler

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    supervisor = Supervisor("Qwen/Qwen2.5-1.5B-Instruct", "0.0.0.0", 9002)
    register_git_handlers(supervisor)
    register_user_handlers(supervisor)
    register_bridge_handler(supervisor)   # 브릿지 핸들러 추가
    supervisor.run()
