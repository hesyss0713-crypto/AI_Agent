CREATE TABLE supervisor_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    requester VARCHAR(100) NOT NULL,     -- 요청자 (user1, user2, ...)
    command VARCHAR(50) NOT NULL,        -- command 종류 (code, search, etc ...)
    code MEDIUMTEXT,                     -- 정제된 코드
    prompt MEDIUMTEXT NOT NULL,          -- User 프롬프트 (입력 메시지)
    supervisor_reply MEDIUMTEXT,         -- Supervisor가 User에게 최종 반환한 전체 텍스트
    filename VARCHAR(500),
    agent_name VARCHAR(100) NOT NULL,    -- 처리 주체 (예: coder)
    parent_id INT NULL,                  -- 이전 요청과 연결
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE coder_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    log_id INT NOT NULL,  -- 어떤 요청의 실행인지
    status ENUM('success','error') NOT NULL,
    output MEDIUMTEXT,    -- 실행 결과 (예: print 출력, 검색결과)
    error_message TEXT,   -- 실패 시 에러 메시지
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_id) REFERENCES supervisor_logs(id)
);