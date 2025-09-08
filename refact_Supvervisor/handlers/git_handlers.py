from utils.message_builder import build_task
from utils.git_utils import extract_repo_name
import os

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"

def register_git_handlers(supervisor):
    dispatcher = supervisor.dispatcher
    socket = supervisor.socket
    git_handler = supervisor.git_handler

    @dispatcher.register("git", "clone_repo")
    def handle_clone(msg):
        if msg.get("result") == "success":
            web_msg = (
                f"{msg['action']} 작업 진행 상황\n"
                f"요청한 repo : {msg['metadata']['stdout']['repo']}\n"
                f"결과 : {msg['result']}\n"
                f"저장 위치 : {msg['metadata']['dir_path']}"
            )
            supervisor._send_to_bridge({
                "type": "info",
                "text": web_msg
            })

            git_url = msg.get("metadata", {}).get("git_url", "")
            dir_name = extract_repo_name(git_url)

            supervisor.last_git_url = git_url
            supervisor.last_dir_name = dir_name

            task = build_task("git", "read_py_files", metadata={"dir_path": f"{dir_name}"})
            socket.send_supervisor_response(task)

    @dispatcher.register("git", "read_py_files")
    def handle_read_files(msg):
        msg["response"] = "[Supervisor] Is this correct?"
        supervisor.py_files = msg

        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name

        # sys summary
        model_summary = git_handler.summarize_experiment(msg, persistent=True)
        supervisor._send_to_bridge({
            "type": "summary",
            "text": model_summary.get("system_summary", "")
        })

        # execute file
        supervisor.execute_file = model_summary.get("execute_file", "train.py")

        # pending 등록 + Bridge 알림
        action_id = supervisor.pending_manager.add("read_py_files", msg)
        supervisor._send_to_bridge({
            "type": "pending",
            "pending_id": action_id,
            "action": "read_py_files",
            "text": msg["response"]
        })

    @dispatcher.register("git", "create_venv")
    def handle_create_venv(msg):
        if msg.get("result") == "success":
            msg["response"] = "Would you like to make modifications, or proceed as is?"

            # pending 등록 + Bridge 알림
            action_id = supervisor.pending_manager.add("git_edit_request", msg)
            supervisor._send_to_bridge({
                "type": "pending",
                "pending_id": action_id,
                "action": "git_edit_request",
                "text": msg["response"]
            })

    @dispatcher.register("git", "edit")
    def handle_edit(msg):
        metadata = msg.get("metadata", {})
        msg["response"] = "Shall we proceed with training using this modification?"

        # 변경된 코드 조합
        comb = []
        for filename, content in metadata.items():
            comb.append(f"\n--- {filename} ---\n{content}\n")
        web_msg = "\n".join(comb)

        supervisor._send_to_bridge({
            "type": "diff",
            "text": web_msg
        })

        # pending 등록 + Bridge 알림
        action_id = supervisor.pending_manager.add("git_edit_confirm", msg)
        supervisor._send_to_bridge({
            "type": "pending",
            "pending_id": action_id,
            "action": "git_edit_confirm",
            "text": msg["response"]
        })

    @dispatcher.register("git", "run_in_venv")
    def handle_result(msg):
        result = msg.get("result", "fail")
        metadata = msg.get("metadata", {})

        if result == "success":
            test_acc = metadata.get("stdout", "N/A")
            supervisor._send_to_bridge({
                "type": "result",
                "text": "\nTraining complete!"
            })
            supervisor._send_to_bridge({
                "type": "result",
                "text": f"Test Accuracy: {test_acc}"
            })
        else:
            err = metadata.get("err", "Unknown error")
            supervisor._send_to_bridge({
                "type": "error",
                "text": f"\nTraining failed.\nError: {err}"
            })
