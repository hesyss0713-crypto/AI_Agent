from utils.message_builder import build_task
from utils.git_utils import extract_repo_name
import os

def register_git_handlers(supervisor):
    dispatcher = supervisor.dispatcher
    socket = supervisor.socket
    git_handler = supervisor.git_handler
    
    @dispatcher.register("git", "clone_repo")
    def handle_clone(msg):
        print(f"받은 task :{msg}")
        if msg.get("result") == "success":
            git_url = msg.get("metadata", {}).get("git_url", "")
            dir_name = extract_repo_name(git_url)
            
            supervisor.last_git_url = git_url
            supervisor.last_dir_name = dir_name

            print("[Supervisor] 환경 세팅 완료.")
            task = build_task("git", "read_py_files", metadata={"dir_path": f"{dir_name}"})
            socket.send_supervisor_response(task)

    @dispatcher.register("git", "read_py_files")
    def handle_read_files(msg):
        print(f"받은 task :{msg}")
        supervisor.py_files = msg

        git_url = supervisor.last_git_url
        dir_name = supervisor.last_dir_name

        # sys summary
        model_summary = git_handler.summarize_experiment(msg, persistent=True)
        print(model_summary["system_summary"])
        
        # execute file 
        supervisor.execute_file = model_summary.get("execute_file", "train.py")
        print(f"[Supervisor] 실행 파일: {supervisor.execute_file}")

        # pending 등록
        action_id = supervisor.pending_manager.add("git_read_confirm", msg)


    @dispatcher.register("git", "create_venv")
    def handle_create_venv(msg):
        if msg.get("result") == "success":
            print(f"받은 task :{msg}")
            # pending 등록
            action_id = supervisor.pending_manager.add("git_edit_request", msg)
            print(f"[Supervisor] 수정할 내용을 입력해주세요: ")

    @dispatcher.register("git", "edit")
    def handle_edit(msg):
        print(f"받은 task :{msg}")
        metadata = msg.get("metadata", {})
        print("\n[Supervisor] Coder가 제안한 코드 수정안:")
        for filename, content in metadata.items():
            print(f"\n--- {filename} ---\n{content}\n")

        # input() 대신 pending 등록
        action_id = supervisor.pending_manager.add("git_edit_confirm", msg)
        print(f"[Supervisor] 이 수정 내용으로 학습을 진행할까요?")

    @dispatcher.register("git", "run_in_venv")
    def handle_result(msg):
        print(f"받은 task :{msg}")
        result = msg.get("result", "fail")
        metadata = msg.get("metadata", {})

        if result == "success":
            test_acc = metadata.get("test_acc", "N/A")
            print("\n[Supervisor] 학습 완료!")
            print(f"[Supervisor]  Test Accuracy: {test_acc}")
        else:
            err = metadata.get("err", "Unknown error")
            print("\n[Supervisor] 학습 실패")
            print(f"[Supervisor] Error: {err}")
