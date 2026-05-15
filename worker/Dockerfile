# YouCloud AI Admin — Worker Node
# Multi-stage build: compile Go, then minimal runtime

# ── Stage 1: Build ──────────────────────────────────────────────────────
FROM golang:1.23-alpine AS builder

WORKDIR /build
COPY go.mod .
COPY *.go ./
RUN go build -o youcloud-worker .

# ── Stage 2: Runtime ────────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

RUN mkdir -p /etc/youcloud

COPY --from=builder /build/youcloud-worker /usr/local/bin/youcloud-worker

# Run as root for /proc and Docker socket access in test environment.
# Hardening (non-root + docker group) will be done before production.

ENTRYPOINT ["/usr/local/bin/youcloud-worker"]
