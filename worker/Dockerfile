# Vigile — Worker Node
# Multi-stage build: compile Go, then minimal runtime

# ── Stage 1: Build ──────────────────────────────────────────────────────
FROM golang:1.23-alpine AS builder

WORKDIR /build
COPY go.mod .
COPY *.go ./
RUN go build -o vigile-worker .

# ── Stage 2: Runtime ────────────────────────────────────────────────────
FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata docker-cli util-linux util-linux-misc || \
    apk add --no-cache ca-certificates tzdata docker-cli util-linux

RUN mkdir -p /etc/vigile /var/log && echo "Vigile syslog bootstrap" > /var/log/syslog

COPY --from=builder /build/vigile-worker /usr/local/bin/vigile-worker

# Run as root for /proc and Docker socket access in test environment.
# Hardening (non-root + docker group) will be done before production.

ENTRYPOINT ["/usr/local/bin/vigile-worker"]
