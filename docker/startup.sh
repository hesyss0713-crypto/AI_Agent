#!/bin/bash

export DISPLAY=:1

# 1. Xvfb 실행
Xvfb :1 -screen 0 1280x720x24 &


# 2. 권한 생성
xauth generate :1 . trusted
xauth add :1 . $(xauth list :1 | awk '{print $3}')

# 3. 윈도우 매니저 실행
fluxbox &

# 4. VNC 서버 실행
x11vnc -display :1 -auth /root/.Xauthority -forever -nopw -shared -bg

# 5. Chrome 실행
google-chrome --no-sandbox --disable-dev-shm-usage --disable-gpu&

# 6. noVNC 실행
/opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen 9005 &

# 7. xrdp 실행
/usr/sbin/xrdp --nodaemon &

# 8. SSH 데몬 실행 (마지막 foreground)
exec /usr/sbin/sshd -D