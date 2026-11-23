FROM eclipse-temurin:21-jre AS java
FROM node:22-bookworm
COPY --from=java /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=/opt/java/openjdk/bin:$PATH
RUN apt-get update && apt-get install -y python3 python3-venv tmux xvfb xauth libgl1-mesa-dev libgles2-mesa-dev libosmesa6-dev libcairo2-dev libpango1.0-dev libjpeg-dev libgif-dev librsvg2-dev libxi-dev libxinerama-dev libxrandr-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ADD source.tar /app/
RUN npm ci
RUN python3 -m venv /venv && /venv/bin/pip install -r requirements.txt
ENV PATH=/venv/bin:$PATH
ENV NODE_OPTIONS=--dns-result-order=ipv4first
