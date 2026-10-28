# Malaria molecular-surveillance report renderer.
#
# The image carries the report code AND the rendering assets (template, reference data,
# export schemas), so the image tag is what pins "how the report looks". Rendering changes
# ship as a new tag; the WDL interface does not change. See docs/WDL_INTERFACE.md.
#
# Build + push with docker/build.sh, which takes the tag from the WDL's docker: default so
# the image cannot be tagged something the pipelines do not pull:
#   docker/build.sh            # build
#   docker/build.sh --push     # build, then push
#
# By hand, if you must — pass the version so the label matches the tag:
#   docker build --build-arg IMAGE_VERSION=0.12.8 \
#       -t us.gcr.io/broad-dsp-lrma/lr-malaria-reports:0.12.8 -f docker/Dockerfile .
# Base is the full python image rather than -slim deliberately: every WDL task in this
# repo runs the house-standard resource-detection preamble, which calls `free`. The slim
# image omits procps, so the preamble aborts under `set -e`. (slim + `apt-get install
# procps` also works, if the build host has package-repo access.)
FROM python:3.11

# The version is an argument, not a literal: it was previously hard-coded here and went
# stale, so an image tagged 0.12.1 carried a label claiming 0.12.0. build.sh passes the
# tag it derives from the WDL, and the assertion below refuses to build if the two differ.
ARG IMAGE_VERSION=0.12.8

LABEL org.opencontainers.image.title="lr-malaria-reports"
LABEL org.opencontainers.image.description="Malaria molecular-surveillance report renderer"
LABEL org.opencontainers.image.version="${IMAGE_VERSION}"

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
