# Malaria molecular-surveillance report renderer.
#
# The image carries the report code AND the rendering assets (template, reference data,
# export schemas), so the image tag is what pins "how the report looks". Rendering changes
# ship as a new tag; the WDL interface does not change. See docs/WDL_INTERFACE.md.
#
# Build + push:
#   docker build -t us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.11.0 -f docker/Dockerfile .
#   docker push  us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.11.0
# Base is the full python image rather than -slim deliberately: every WDL task in this
# repo runs the house-standard resource-detection preamble, which calls `free`. The slim
# image omits procps, so the preamble aborts under `set -e`. (slim + `apt-get install
# procps` also works, if the build host has package-repo access.)
FROM python:3.11

LABEL org.opencontainers.image.title="lr-malaria-reports"
LABEL org.opencontainers.image.description="Senegal malaria molecular-surveillance report renderer"
LABEL org.opencontainers.image.version="0.11.0"

# The report pipeline is pure standard-library Python 3 by design: no third-party
# packages, so there is nothing to resolve at build time and nothing to drift.
WORKDIR /opt/malaria_reports
COPY scripts/   /opt/malaria_reports/scripts/
COPY templates/ /opt/malaria_reports/templates/
COPY reference/ /opt/malaria_reports/reference/
COPY schemas/   /opt/malaria_reports/schemas/

ENV PATH="/opt/malaria_reports/scripts:${PATH}"
ENV PYTHONDONTWRITEBYTECODE=1

# fail the build if the entrypoint or its assets are broken
RUN command -v free > /dev/null \
 && command -v tar  > /dev/null \
 && python3 /opt/malaria_reports/scripts/make_report.py --help > /dev/null \
 && python3 -c "import sys; sys.path.insert(0,'/opt/malaria_reports/scripts'); \
import gen_reports as G; assert len(G.MK) > 0; print('markers:', len(G.MK))"

CMD ["python3", "/opt/malaria_reports/scripts/make_report.py", "--help"]
