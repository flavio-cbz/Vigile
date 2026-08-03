#!/usr/bin/env bash
set -euo pipefail

# Vigile — Worker Cross-Compilation Script
# Builds zero-dependency static Go binaries for supported architectures and generates release manifests.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
WORKER_DIR="${ROOT_DIR}/worker"
OUTPUT_DIR="${ROOT_DIR}/master/static/releases"

mkdir -p "${OUTPUT_DIR}"

VERSION="${1:-2.3.0}"
echo "==> Building Vigile Worker v${VERSION} static binaries..."

PLATFORMS=(
    "linux/amd64"
    "linux/arm64"
    "darwin/amd64"
    "darwin/arm64"
)

for PLATFORM in "${PLATFORMS[@]}"; do
    GOOS="${PLATFORM%/*}"
    GOARCH="${PLATFORM#*/}"
    BINARY_NAME="worker-${GOOS}-${GOARCH}"
    if [ "${GOOS}" = "windows" ]; then
        BINARY_NAME="${BINARY_NAME}.exe"
    fi
    OUT_PATH="${OUTPUT_DIR}/${BINARY_NAME}"

    echo "    Compiling for ${GOOS}/${GOARCH} -> ${OUT_PATH}..."
    (cd "${WORKER_DIR}" && CGO_ENABLED=0 GOOS="${GOOS}" GOARCH="${GOARCH}" go build \
        -buildvcs=false \
        -ldflags="-s -w -X main.version=${VERSION}" \
        -o "${OUT_PATH}" .)

    # Compute SHA256
    if command -v shasum &>/dev/null; then
        SHA256=$(shasum -a 256 "${OUT_PATH}" | awk '{print $1}')
    else
        SHA256=$(sha256sum "${OUT_PATH}" | awk '{print $1}')
    fi
    echo "${SHA256}" > "${OUT_PATH}.sha256"

    echo "    SUCCESS: ${BINARY_NAME} (${SHA256})"
done

echo "==> All static worker binaries built successfully in ${OUTPUT_DIR}"
