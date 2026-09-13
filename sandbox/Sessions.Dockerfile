# Small compatibility rebuild. Supply an immutable private base image at build
# time, for example with --build-arg SESSION_BASE=registry.example/...@sha256:...
ARG SESSION_BASE
FROM ${SESSION_BASE}
USER root
COPY sandbox/python/session-compat.lock /opt/lab-session-compat.lock
RUN uv pip install --system --no-cache --require-hashes --exclude-newer 2026-09-02 -r /opt/lab-session-compat.lock
COPY sandbox/azure_execute.py sandbox/session_server.py /opt/lab/
EXPOSE 8080
CMD ["python", "/opt/lab/session_server.py"]
