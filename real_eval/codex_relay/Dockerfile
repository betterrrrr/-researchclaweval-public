FROM python:3.11-slim
WORKDIR /app
RUN groupadd --system relay && useradd --system --gid relay --home-dir /app relay
COPY --chown=relay:relay relay.py /app/relay.py
RUN chmod 0555 /app/relay.py
EXPOSE 8787
USER relay
CMD ["python", "/app/relay.py"]
