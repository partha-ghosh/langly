FROM alpine
RUN apk update && apk upgrade
RUN apk add python3
RUN python -m venv /home/venv
ENV PATH=/home/venv/bin:$PATH
RUN pip install flask flask_socketio deep_translator gTTS

# https://github.com/Hax4us/TermuxAlpine
# docker build -t alpine:1.0 .
# docker run -d -p 8050:8050 -v .:/opt/app alpine:1.0 bash -c "cd /opt/app && python app.py"