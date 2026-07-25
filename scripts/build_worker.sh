#!/usr/bin/env bash
# Vigile — Worker Cross-Compilation Pipeline
#
# Compiles the Go worker for all supported platforms,
# generates SHA-256 checksums, and produces a release manifest.
#
# Usage:
#   ./scripts/build_worker.sh                  # build all targets
#   ./scripts/build_worker.sh --target linux/amd64  # single target
#   ./scripts/build_worker.sh --help            # this message
#
# Prerequisites: go (1.23+), sha256sum, jq

set -euo pipefail

# ── Defaults ───────────────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist/worker"
WORKER_DIR="$PROJECT_ROOT/worker"
SINGLE_TARGET=""

# ── CLI parsing ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      SINGLE_TARGET="$2"; shift 2 ;;
    --help|-h)
      echo "Usage: $0 [--target OS/ARCH] [--help]"
      echo ""
      echo "Cross-compile the Vigile Go worker for all supported platforms."
      echo ""
      echo "Options:"
      echo "  --target OS/ARCH   Build only a single target (e.g. linux/amd64)"
      echo "  --help, -h         Show this message"
      echo ""
      echo "Supported targets:"
      echo "  linux/amd64       Linux x86-64"
      echo "  linux/arm64       Linux ARM64 (Raspberry Pi 4/5, ARM servers)"
      echo "  darwin/arm64      macOS Apple Silicon"
      echo "  freebsd/amd64     FreeBSD x86-64 (TrueNAS Core)"
      echo ""
      echo "Output: dist/worker/{os}/{arch}/worker + .sha256 + manifest.json"
      exit 0 ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--target OS/ARCH] [--help]"
      exit 1 ;;
  esac
done

# ── Version detection ──────────────────────────────────────────────────
VERSION=$(grep -oP 'const VERSION\s*=\s*"\K[^"]+' "$WORKER_DIR/discovery.go" 2>/dev/null || echo "1.0.0")
BUILD_DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
GO_VERSION=$(go version | grep -oP 'go\K[0-9]+\.[0-9]+\.[0-9]+' || echo "unknown")

echo "========================================="
echo "  Vigile Worker Build Pipeline"
echo "========================================="
echo ""
echo "  Version:    v$VERSION"
echo "  Build date: $BUILD_DATE"
echo "  Go version: $GO_VERSION"
echo ""

# ── Target matrix ──────────────────────────────────────────────────────
ALL_TARGETS=(
  "linux:amd64"
  "linux:arm64"
  "darwin:arm64"
  "freebsd:amd64"
)

# Filter to single target if requested
TARGETS=()
if [ -n "$SINGLE_TARGET" ]; then
  IFS='/' read -r req_os req_arch <<< "$SINGLE_TARGET"
  for t in "${ALL_TARGETS[@]}"; do
    IFS=':' read -r t_os t_arch <<< "$t"
    if [ "$t_os" = "$req_os" ] && [ "$t_arch" = "$req_arch" ]; then
      TARGETS+=("$t")
      break
    fi
  done
  if [ ${#TARGETS[@]} -eq 0 ]; then
    echo "ERROR: Unknown target '$SINGLE_TARGET'"
    echo "Supported: linux/amd64, linux/arm64, darwin/arm64, freebsd/amd64"
    exit 1
  fi
  echo "=== Building single target: $SINGLE_TARGET ==="
  echo ""
else
  TARGETS=("${ALL_TARGETS[@]}")
fi

# ── Idempotent clean: rebuild dist/worker from scratch ─────────────────
if [ -z "$SINGLE_TARGET" ]; then
  echo "=== Cleaning dist/worker/ ==="
  rm -rf "$DIST_DIR"
  echo ""
fi

# ── Build each target ──────────────────────────────────────────────────
BUILD_START=$(date +%s)
BINARIES_JSON="[]"

for target in "${TARGETS[@]}"; do
  IFS=':' read -r GOOS GOARCH <<< "$target"
  OUT_DIR="$DIST_DIR/$GOOS/$GOARCH"
  OUT_BIN="$OUT_DIR/worker"

  echo "=== Building $GOOS/$GOARCH ==="
  mkdir -p "$OUT_DIR"

  (
    cd "$WORKER_DIR"
    GOOS="$GOOS" GOARCH="$GOARCH" CGO_ENABLED=0 \
      go build -trimpath -ldflags="-s -w" -o "$OUT_BIN" .
  )

  # Generate SHA-256 checksum (format: hash + filename for sha256sum -c)
  ( cd "$OUT_DIR" && sha256sum worker > worker.sha256 )
  SHA256=$(awk '{print $1}' "$OUT_DIR/worker.sha256")
  SIZE=$(stat -c%s "$OUT_BIN" 2>/dev/null || stat -f%z "$OUT_BIN" 2>/dev/null)

  echo "  Binary: $(ls -lh "$OUT_BIN" | awk '{print $5}')"
  echo "  SHA256: $SHA256"
  echo ""

  # Append to JSON array (jq is available — safe to use)
  BINARIES_JSON=$(echo "$BINARIES_JSON" | jq -c \
    --arg os "$GOOS" \
    --arg arch "$GOARCH" \
    --arg path "$GOOS/$GOARCH/worker" \
    --arg sha256 "$SHA256" \
    --argjson size "$SIZE" \
    '. + [{$os, $arch, $path, $sha256, $size}]')
done

# ── Manifest ───────────────────────────────────────────────────────────
BUILD_END=$(date +%s)
BUILD_SECONDS=$((BUILD_END - BUILD_START))

jq -n \
  --arg version "$VERSION" \
  --arg build_date "$BUILD_DATE" \
  --arg go_version "$GO_VERSION" \
  --argjson build_seconds "$BUILD_SECONDS" \
  --argjson binaries "$BINARIES_JSON" \
  '{
    version: $version,
    build_date: $build_date,
    go_version: $go_version,
    build_seconds: $build_seconds,
    binaries: $binaries
  }' > "$DIST_DIR/manifest.json"

echo "=== Manifest ==="
echo "  $DIST_DIR/manifest.json"
echo ""

# ── Deploy to worker-dist (served by Master) ──────────────────────────────
# The Master maps data/worker-dist → /var/cache/vigile/worker and serves
# binaries from {cache_dir}/{os}/{arch}/worker.  We must deploy both the
# binaries and the manifest there so the UPDATE_WORKER auto-update path
# delivers the freshly-built binary instead of a stale one.
WORKER_DIST="$PROJECT_ROOT/data/worker-dist"
if [ -d "$WORKER_DIST" ]; then
  echo "=== Deploying to data/worker-dist/ ==="
  for target in "${TARGETS[@]}"; do
    IFS=':' read -r GOOS GOARCH <<< "$target"
    SRC="$DIST_DIR/$GOOS/$GOARCH"
    DST="$WORKER_DIST/$GOOS/$GOARCH"
    mkdir -p "$DST"
    cp "$SRC/worker" "$DST/worker"
    cp "$SRC/worker.sha256" "$DST/worker.sha256"
    cp "$SRC/worker.sig" "$DST/worker.sig" 2>/dev/null || true
    echo "  $GOOS/$GOARCH/worker  →  $DST/worker"
  done

  # Regenerate manifest with file:// URLs for local serving.
  # The Master mounts data/worker-dist at /var/cache/vigile/worker,
  # so file:// URLs must point to that mount path.
  MANIFEST_BINARIES="[]"
  for target in "${TARGETS[@]}"; do
    IFS=':' read -r GOOS GOARCH <<< "$target"
    SHA256=$(awk '{print $1}' "$WORKER_DIST/$GOOS/$GOARCH/worker.sha256")
    SIZE=$(stat -c%s "$WORKER_DIST/$GOOS/$GOARCH/worker" 2>/dev/null || stat -f%z "$WORKER_DIST/$GOOS/$GOARCH/worker" 2>/dev/null)
    MANIFEST_BINARIES=$(echo "$MANIFEST_BINARIES" | jq -c \
      --arg os "$GOOS" \
      --arg arch "$GOARCH" \
      --arg url "file:///var/cache/vigile/worker/$GOOS/$GOARCH/worker" \
      --arg sha256 "$SHA256" \
      --argjson size "$SIZE" \
      '. + [{$os, $arch, $url, $sha256, $size}]')
  done

  jq -n \
    --arg version "$VERSION" \
    --arg build_date "$BUILD_DATE" \
    --argjson binaries "$MANIFEST_BINARIES" \
    '{
      version: $version,
      released_at: $build_date,
      channel: "stable",
      binaries: $binaries
    }' > "$WORKER_DIST/manifest.json"

  echo "  manifest.json  →  $WORKER_DIST/manifest.json"
  echo ""
fi

# ── Summary ────────────────────────────────────────────────────────────
echo "========================================="
echo "  Build Complete"
echo "========================================="
echo ""
echo "Version:    v$VERSION"
echo "Duration:   ${BUILD_SECONDS}s"
echo ""
for target in "${TARGETS[@]}"; do
  IFS=':' read -r GOOS GOARCH <<< "$target"
  BIN="$DIST_DIR/$GOOS/$GOARCH/worker"
  SIZE=$(ls -lh "$BIN" | awk '{print $5}')
  TYPE=$(file -b "$BIN" 2>/dev/null | cut -d',' -f1)
  echo "  $GOOS/$GOARCH     $SIZE    $TYPE"
done
echo ""
echo "Output: $DIST_DIR/"
find "$DIST_DIR" -type f \( -name "worker" -o -name "manifest.json" \) 2>/dev/null | sort
