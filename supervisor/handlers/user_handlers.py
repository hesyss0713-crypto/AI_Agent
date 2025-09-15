from utils.message_builder import build_task
from utils.git_utils import extract_repo_name

def register_user_handlers(supervisor):
    dispatcher = supervisor.dispatcher
    router = supervisor.router
    socket = supervisor.socket
    git_handler = supervisor.git_handler
    intent_cls = supervisor.intent_cls
    llm = supervisor.llm
    bridge = supervisor._send_to_bridge

    # 일반 입력 처리 (Normal)

    @dispatcher.register(None, "user_input_normal")
    def handle_user_input_normal(msg):
        text = msg["text"]
        command, persistent = router.get_command(text)

        if command in ("git", "code"):
            supervisor.last_tab_id += 1
            tab_id = supervisor.last_tab_id
            supervisor.active_tabe = tab_id
        
        else:
            tab_id = supervisor.active_tab or 1

        if command == "git":
            url = git_handler.handle(text, persistent=persistent)
            task = build_task("git", "clone_repo", metadata={"git_url": url, "tabId": tab_id})
            socket.send_supervisor_response(task)

        elif command == "conversation":
            response = llm.run_with_prompt("you are a helpful assistant", text, 512, True)
            bridge("main_input",response)
            
        elif command == "code":
            print(f"")
            
        else:
            print(f"[Supervisor] Unkown command: {command}")

    # Pending 응답 처리

    @dispatcher.register(None, "user_input_pending")
    def handle_user_input_pending(msg):
        text = msg["text"]
        pending = msg["pending"]
        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name
        mtype = "pending_request"
        tab_id = supervisor.active_tab

        if pending["type"] == "read_py_files":
            print(pending)
            supervisor._send_to_bridge(mtype, pending['msg']["response"], tab_id)
            intent = intent_cls.get_intent(text, pending['msg']["response"])
            supervisor._send_to_bridge(mtype, f"your intent : {intent}", tab_id)
            if intent == "positive":
                task = build_task("git", "create_venv",
                                  metadata={"dir_path": f"{dir_name}/",
                                            "requirements": "requirements.txt",
                                            "tabId": tab_id})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                print(f"[Supervisor] It has been canceled.")

        elif pending["type"] == "git_edit_request":
            supervisor._send_to_bridge(mtype, pending['msg']["response"], tab_id)
            intent = intent_cls.get_intent(text, pending['msg']["response"])
            supervisor._send_to_bridge(mtype, f"your intent : {intent}", tab_id)

            if intent == 'revise':
                target, metadata = git_handler.generate_edit_task(text, supervisor.py_files, persistent=True)
                metadata["tabId"] = tab_id
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
                    "skip_edit": True,
                    "tabId" : tab_id 
                    }
                )
                socket.send_supervisor_response(task)
            
        elif pending["type"] == "git_edit_confirm":
            supervisor._send_to_bridge(mtype, pending['msg']["response"], tab_id)
            intent = intent_cls.get_intent(text, pending['msg']["response"])
            supervisor._send_to_bridge(mtype, f"your intent : {intent}", tab_id)
            if intent == "positive":
                task = build_task("git", "run_in_venv", target=supervisor.execute_file,
                                  metadata={"cwd": f"{dir_name}/",
                                            "venv_path": f"{dir_name}/venv",
                                            "tabId": tab_id})
                socket.send_supervisor_response(task)
            elif intent == "negative":
                supervisor._send_to_bridge(mtype, "Modification has been canceled.", tab_id)
            elif intent == "revise":
                supervisor._send_to_bridge(mtype, "수정 재요청", tab_id)
