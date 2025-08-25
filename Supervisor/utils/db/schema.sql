-- ENUM 타입 정의
CREATE TYPE status_enum AS ENUM ('success', 'error');

CREATE TABLE supervisor_logs (
    id SERIAL PRIMARY KEY,
    requester VARCHAR(100) NOT NULL,
    command VARCHAR(50) NOT NULL,
    code TEXT,
    prompt TEXT NOT NULL,
    supervisor_reply TEXT,
    filename VARCHAR(500),
    agent_name VARCHAR(100) NOT NULL,
    parent_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE coder_logs (
    id SERIAL PRIMARY KEY,
    log_id INT NOT NULL,
    status status_enum NOT NULL,
    output TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (log_id) REFERENCES supervisor_logs(id)
);