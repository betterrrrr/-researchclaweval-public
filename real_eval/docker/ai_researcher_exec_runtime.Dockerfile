FROM nvcr.io/nvidia/pytorch:25.11-py3
USER root
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility
RUN apt-get update && apt-get install -y --no-install-recommends \
        supervisor netcat-traditional && rm -rf /var/lib/apt/lists/*
COPY AI-Researcher/docker/tcp_server.py /app/tcp_server.py
COPY AI-Researcher/docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
RUN mkdir -p /var/log/supervisor /workplace
EXPOSE 8000
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]