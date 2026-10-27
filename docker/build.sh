#!/usr/bin/env bash
# Build (and optionally push) the report image at the version the WDL actually pulls.
#
# The tag is not a parameter. It is read from the `docker:` default in
# wdl/tasks/Malaria/SurveillanceReport.wdl, because that is what Terra will pull: a tag
# chosen on the command line can disagree with it, and silently did — the pipelines were
# pinned to 0.12.1 while the Dockerfile labelled itself 0.12.0 and the docs told you to
# build 0.12.0.
#
#   docker/build.sh            build
#   docker/build.sh --push     build, then push
set -euo pipefail
cd "$(dirname "$0")/.."

TASKS=wdl/tasks/Malaria/SurveillanceReport.wdl

# every task must pin the same image, or "the" version is a fiction
mapfile -t IMAGES < <(grep -oE 'us\.gcr\.io/broad-dsp-lrma/lr-malaria-reports:[0-9A-Za-z._-]+' "$TASKS" | sort -u)
if [[ ${#IMAGES[@]} -ne 1 ]]; then
    echo "ERROR: $TASKS pins ${#IMAGES[@]} different images; they must agree:" >&2
    printf '  %s\n' "${IMAGES[@]}" >&2
    exit 1
fi
IMAGE="${IMAGES[0]}"
VERSION="${IMAGE##*:}"

# the meta tool_version is what shows up in provenance; keep it honest too
mapfile -t TOOLVERS < <(grep -oE 'tool_version:[[:space:]]*"[^"]+"' "$TASKS" | grep -oE '"[^"]+"' | tr -d '"' | sort -u)
if [[ ${#TOOLVERS[@]} -ne 1 || "${TOOLVERS[0]}" != "$VERSION" ]]; then
    echo "ERROR: tool_version in $TASKS is ${TOOLVERS[*]}, but the docker tag is $VERSION" >&2
    exit 1
fi

echo "building $IMAGE (version $VERSION, from $TASKS)"
docker build --build-arg "IMAGE_VERSION=$VERSION" -t "$IMAGE" -f docker/Dockerfile .

# prove the label matches the tag rather than trusting the build arg plumbing
LABELLED=$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$IMAGE")
if [[ "$LABELLED" != "$VERSION" ]]; then
    echo "ERROR: built image is labelled '$LABELLED' but tagged '$VERSION'" >&2
    exit 1
fi
echo "built $IMAGE; label and tag both $VERSION"

if [[ "${1:-}" == "--push" ]]; then
    echo "pushing $IMAGE"
    docker push "$IMAGE"
    echo "pushed $IMAGE"
else
    echo
    echo "to push:  docker/build.sh --push"
    echo "      or:  docker push $IMAGE"
fi
