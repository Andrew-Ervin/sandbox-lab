# Local incremental update: reuse installed toolchains instead of downloading them again.
FROM sandbox-lab/developer:local AS installed
FROM sandbox-lab/project:local AS ai
USER root
COPY --from=installed /usr/local/lib/node_modules/@earendil-works/pi-coding-agent /usr/local/lib/node_modules/@earendil-works/pi-coding-agent
COPY --from=installed /usr/local/bin/ori /usr/local/bin/ori
RUN ln -s ../lib/node_modules/@earendil-works/pi-coding-agent/dist/cli.js /usr/local/bin/pi
COPY sandbox/agent.py sandbox/harness_setup.py sandbox/package_setup.py /opt/lab/
ENV PI_TELEMETRY=0 ORI_TELEMETRY=0 ORI_NO_UPDATE_CHECK=1
USER 1000:1000
FROM installed AS developer
USER root
COPY sandbox/agent.py sandbox/harness_setup.py sandbox/package_setup.py /opt/lab/
COPY sandbox/pi-chat /opt/lab/pi-chat
USER 1000:1000

FROM sandbox-lab/quick:local AS quick
COPY sandbox/checkpoint.py sandbox/collect.py sandbox/quick.py sandbox/plot_capture.py sandbox/render_plot.py /opt/lab/
