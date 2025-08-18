import mysql.connector
import json


class DBManager:
    def __init__(self, host="localhost", user="supervisor_user", password="supervisor_pass", database="supervisor_db"):
        self.conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=9001
        )
        # dict 형태로 반환
        self.cursor = self.conn.cursor(dictionary=True)

    # ------------------------------
    # 1. supervisor_logs 관리
    # ------------------------------
    def insert_supervisor_log(self, requester, command, code, prompt, agent_name,
                              supervisor_reply=None, filename=None, parent_id=None):
        """
        supervisor_logs 테이블에 요청 로그 저장
        """
        sql = """
        INSERT INTO supervisor_logs
        (requester, command, code, prompt, supervisor_reply, filename, agent_name, parent_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (requester, command, code, prompt, supervisor_reply, filename, agent_name, parent_id)

        self.cursor.execute(sql, values)
        self.conn.commit()
        return self.cursor.lastrowid  # 새 id 반환

    def get_supervisor_log(self, log_id):
        """
        특정 supervisor 로그 조회
        """
        sql = "SELECT * FROM supervisor_logs WHERE id=%s"
        self.cursor.execute(sql, (log_id,))
        return self.cursor.fetchone()

    # ------------------------------
    # 2. coder_logs 관리
    # ------------------------------
    def insert_coder_log(self, log_id, status, output=None, error_message=None):
        """
        coder_logs 테이블에 실행 결과 저장
        """
        sql = """
        INSERT INTO coder_logs
        (log_id, status, output, error_message)
        VALUES (%s, %s, %s, %s)
        """
        values = (log_id, status, output, error_message)

        self.cursor.execute(sql, values)
        self.conn.commit()
        return self.cursor.lastrowid

    def get_coder_logs(self, log_id):
        """
        특정 supervisor 요청에 대한 모든 coder 실행 로그 조회
        """
        sql = "SELECT * FROM coder_logs WHERE log_id=%s"
        self.cursor.execute(sql, (log_id,))
        return self.cursor.fetchall()

    # ------------------------------
    # 3. 공통
    # ------------------------------
    def close(self):
        self.cursor.close()
        self.conn.close()
