from utils.message_builder import build_task
from utils.git_utils import extract_repo_name

def register_user_handlers(supervisor):
    dispatcher = supervisor.dispatcher
    router = supervisor.router
    socket = supervisor.socket
    git_handler = supervisor.git_handler
    intent_cls = supervisor.intent_cls


    # 일반 입력 처리 (Normal)

    @dispatcher.register(None, "user_input_normal")
    def handle_user_input_normal(msg):
        text = msg["text"]
        command, persistent = router.get_command(text)

        if command == "git":
            url = git_handler.handle(text, persistent=persistent)
            task = build_task("git", "clone_repo", metadata={"git_url": url})
            socket.send_supervisor_response(task)

        elif command == "conversation":
            response = supervisor.llm.chat(text)
            print(f"[Conversation] {response}")

        elif command == "search":
            print(f"[Supervisor] Unkown command: {command}")

        elif command == "agent":
            print(f"[Supervisor] Unkown command: {command}")

        else:
            print(f"[Supervisor] Unkown command: {command}")

    # Pending 응답 처리

    @dispatcher.register(None, "user_input_pending")
    def handle_user_input_pending(msg):
        text = msg["text"]
        pending = msg["pending"]
        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name

        if pending["type"] == "read_py_files":
            intent = intent_cls.get_intent(text, pending['msg']["response"])
            if intent == "positive":
                task = build_task("git", "create_venv",
                                  metadata={"dir_path": f"{dir_name}/",
                                            "requirements": "requirements.txt"})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                print("[Supervisor] It has been canceled.")

        elif pending["type"] == "git_edit_request":
            intent = intent_cls.get_intent(text, pending['msg']["response"])

            if intent == 'revise':
                target, metadata = git_handler.generate_edit_task(text, supervisor.py_files, persistent=True)
                task = build_task("git", "edit", target=target, metadata=metadata)
                socket.send_supervisor_response(task)
            
            elif intent == "direct":
                task = build_task(
                "git",
                "run_in_venv",
                target=supervisor.execute_file,   # ex) train.py
                metadata={
                    "cwd": f"{dir_name}/",
                    "venv_path": f"{dir_name}/venv",
                    "skip_edit": True  
                    }
                )
                socket.send_supervisor_response(task)
            
        elif pending["type"] == "git_edit_confirm":
            intent = intent_cls.get_intent(text, pending['msg']["response"])
            if intent == "positive":
                task = build_task("git", "run_in_venv", target=supervisor.execute_file,
                                  metadata={"cwd": f"{dir_name}/",
                                            "venv_path": f"{dir_name}/venv"})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                print("[Supervisor] Modification has been canceled.")
            elif intent == "revise":
                print("[Supervisor] 수정 재요청")
