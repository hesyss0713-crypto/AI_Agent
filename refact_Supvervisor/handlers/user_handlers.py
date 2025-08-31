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
            print(f"[Supervisor] 알 수 없는 command: {command}")

        elif command == "agent":
            print(f"[Supervisor] 알 수 없는 command: {command}")

        else:
            print(f"[Supervisor] 알 수 없는 command: {command}")

    # Pending 응답 처리

    @dispatcher.register(None, "user_input_pending")
    def handle_user_input_pending(msg):
        text = msg["text"]
        pending = msg["pending"]
        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name

        if pending["type"] == "git_read_confirm":
            intent = intent_cls.get_intent(text)
            if intent == "positive":
                task = build_task("git", "create_venv",
                                  metadata={"dir_path": f"{dir_name}/",
                                            "requirements": "requirements.txt"})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                print("[Supervisor] 취소되었습니다.")

        elif pending["type"] == "git_edit_request":
            edit_input = text
            target, metadata = git_handler.generate_edit_task(edit_input, supervisor.py_files, persistent=True)
            task = build_task("git", "edit", target=target, metadata=metadata)
            socket.send_supervisor_response(task)

        elif pending["type"] == "git_edit_confirm":
            intent = intent_cls.get_intent(text)
            if intent == "positive":
                task = build_task("git", "run_in_venv", target=supervisor.execute_file[0],
                                  metadata={"cwd": f"{dir_name}/",
                                            "venv_path": f"{dir_name}/venv"})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                print("[Supervisor] 수정이 취소되었습니다.")
            elif intent == "revise":
                print("[Supervisor] 수정 재요청")
