# AI_Agent
AI_Agent
# command on linux

cd /AI_Agent or your pull repository

sudo docker buildx build -t coder:latest -f  ./dockerbuild --load .
sudo docker run -it -p 9006:9006 -p 9007:9007 -p 9008:9008 -p 9009:9009 -p 9010:9010 coder

If you change your vnc port then edit your dockerbuild and startup.sh

## startup.sh
/opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen 9006 &
## dockerbuild
EXPOSE 9006 9007 9008 9009 9010

<img width="1916" height="1020" alt="image" src="https://github.com/user-attachments/assets/a0a44bad-1744-413c-b6da-0362f5e0052a" />
