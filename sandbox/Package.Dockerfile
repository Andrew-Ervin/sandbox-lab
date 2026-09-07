FROM sandbox-lab/gateway:local
USER root
COPY sandbox/package_gateway.py /app/package_gateway.py
USER 1000:1000
CMD ["uvicorn", "package_gateway:app", "--app-dir", "/app", "--host", "0.0.0.0", "--port", "3128", "--no-access-log"]
