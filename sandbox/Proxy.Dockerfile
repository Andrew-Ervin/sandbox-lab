FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends squid ca-certificates && rm -rf /var/lib/apt/lists/* && chown -R 1000:1000 /var/log/squid /var/spool/squid
USER 1000:1000
