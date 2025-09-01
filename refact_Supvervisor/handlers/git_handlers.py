from utils.message_builder import build_task
from utils.git_utils import extract_repo_name
import os

YELLOW = "\033[93m"
RESET = "\033[0m"

def register_git_handlers(supervisor):
    dispatcher = supervisor.dispatcher
    socket = supervisor.socket
    git_handler = supervisor.git_handler
    
    @dispatcher.register("git", "clone_repo")
    def handle_clone(msg):
        # print(f"받은 task :{msg}")
        if msg.get("result") == "success":
            git_url = msg.get("metadata", {}).get("git_url", "")
            dir_name = extract_repo_name(git_url)
            
            supervisor.last_git_url = git_url
            supervisor.last_dir_name = dir_name

            task = build_task("git", "read_py_files", metadata={"dir_path": f"{dir_name}"})
            socket.send_supervisor_response(task)

    @dispatcher.register("git", "read_py_files")
    def handle_read_files(msg):
        # print(f"받은 task :{msg}")
        msg["response"] = "[Supervisor] Is this correct?"
        supervisor.py_files = msg

        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name

        # sys summary
        model_summary = git_handler.summarize_experiment(msg, persistent=True)
        print(model_summary["system_summary"])
        
        # execute file 
        supervisor.execute_file = model_summary.get("execute_file", "train.py")
        print(f"{YELLOW}[Supervisor] 실행 파일: {supervisor.execute_file}{RESET}")

        # pending 등록
        action_id = supervisor.pending_manager.add("read_py_files", msg)


    @dispatcher.register("git", "create_venv")
    def handle_create_venv(msg):
        if msg.get("result") == "success":
            msg["response"] = "[Supervisor] Would you like to make modifications, or proceed as is?"
            
            # pending 등록
            action_id = supervisor.pending_manager.add("git_edit_request", msg)
            

    @dispatcher.register("git", "edit")
    def handle_edit(msg):
        metadata = msg.get("metadata", {})
        msg["response"] = "[Supervisor] Shall we proceed with training using this modification?"
        print(f"{YELLOW}\n[Supervisor] Code modification proposed by the Coder:{RESET}")
        for filename, content in metadata.items():
            print(f"\n--- {filename} ---\n{content}\n")

        # input() 대신 pending 등록
        action_id = supervisor.pending_manager.add("git_edit_confirm", msg)

    @dispatcher.register("git", "run_in_venv")
    def handle_result(msg):
        # print(f"받은 task :{msg}")
        result = msg.get("result", "fail")
        metadata = msg.get("metadata", {})

        if result == "success":
            test_acc = metadata.get("stdout", "N/A")
            print(f"{YELLOW}\n[Supervisor] Training complete!{RESET}")
            print(f"[Supervisor]  Test Accuracy: {print(test_acc)}")
        else:
            err = metadata.get("err", "Unknown error")
            print(f"{YELLOW}\n[Supervisor] Training failed.{RESET}")
            print(f"[Supervisor] Error: {err}")
