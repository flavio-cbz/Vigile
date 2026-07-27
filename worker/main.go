// Vigile — Worker Node
//
// Autonomous agent that connects to the Master via WebSocket,
// authenticates with Ed25519, and executes whitelisted actions.
//
// Zero external dependencies — stdlib Go only.
//
// Usage:
//
//	vigile-worker --master http://master:8000 --token <JOIN_TOKEN>
//
// Or use persisted config:
//
//	/etc/vigile/master_url
//	/etc/vigile/enrollment.token
package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
)

// Logger for structured output (stdout for journald collection).

func main() {
	// ── CLI flags ────────────────────────────────────────────────────────
	masterURL := flag.String("master", os.Getenv("MASTER_URL"), "Master WebSocket URL (e.g. https://master:8443)")
	joinToken := flag.String("token", os.Getenv("JOIN_TOKEN"), "JOIN_TOKEN for enrollment")
	keyDir := flag.String("key-dir", os.Getenv("VIGILE_KEY_DIR"), "Directory for keys and config (default: /etc/vigile or %ProgramData%\\vigile on Windows)")
	flag.Parse()

	if *keyDir != "" {
		setKeyDir(*keyDir)
	}

	// ── Resolve master URL ───────────────────────────────────────────────
	url := getMasterURL(*masterURL)
	if url == "" {
		slog.Error("MASTER_URL is required. Set --master flag or write to /etc/vigile/master_url")
	os.Exit(1)
	}

	allowInsecure := os.Getenv("ALLOW_INSECURE") == "true"

	// Normalize: ensure http/https scheme for WebSocket upgrade
	if !strings.HasPrefix(url, "http://") && !strings.HasPrefix(url, "https://") &&
		!strings.HasPrefix(url, "ws://") && !strings.HasPrefix(url, "wss://") {
		// No scheme: default to https
		url = "https://" + url
	}

	if strings.HasPrefix(url, "ws://") {
		url = "http://" + url[5:]
	} else if strings.HasPrefix(url, "wss://") {
		url = "https://" + url[6:]
	}

	if strings.HasPrefix(url, "http://") && !allowInsecure {
		slog.Error("FATAL: Unencrypted connection (HTTP/WS) is forbidden by default. Set ALLOW_INSECURE=true to bypass.")
	os.Exit(1)
	}

	slog.Info("Vigile Worker starting")
	if allowInsecure {
		slog.Warn("ALLOW_INSECURE=true is set. Traffic to the Master will not be encrypted. DO NOT USE IN PRODUCTION!")
	} else {
		slog.Info("secure transport enforced (HTTPS/WSS)")
	}
	slog.Info("Master URL", "url", url)

	// ── Load worker token from disk (for reconnection) ───────────────────
	workerToken, err := readWorkerToken()
	if err != nil {
		slog.Warn("failed to read worker token", "error", err)
	}
	if workerToken != "" {
		slog.Info("Worker token loaded from disk — reconnecting with existing identity")
	}

	// ── Resolve join token (not required if worker token exists) ────────
	token, err := readJoinToken(*joinToken)
	if err != nil {
		if workerToken != "" {
			slog.Info("No JOIN_TOKEN (already consumed) — using worker token for reconnect")
			token = ""
		} else {
			slog.Error("Failed to read JOIN_TOKEN", "error", err)
		os.Exit(1)
		}
	}
	if token != "" {
		slog.Info("JOIN_TOKEN hash", "hash", computeTokenHash(token))
	}

	// ── Load or generate Ed25519 keypair ─────────────────────────────────
	privKey, pubKey, err := loadOrGenerateKeypair()
	if err != nil {
		slog.Error("Failed to load/generate keypair", "error", err)
		os.Exit(1)
	}
	slog.Info("Ed25519 public key loaded", "bytes", len(pubKey))

	// ── Collect fingerprint ──────────────────────────────────────────────
	fp := collectFingerprint()
	slog.Info("Fingerprint", "hostname", fp.Hostname, "arch", fp.Arch, "os", fp.OS)

	// ── Create lifecycle context (cancelled on SIGINT/SIGTERM) ───────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("PANIC in signal handler", "recover", r)
			}
		}()
		sig := <-sigCh
		slog.Info("Received signal", "signal", sig)
		cancel()
	}()

	// ── Create worker connection ─────────────────────────────────────────
	wc := NewWorkerConn(ctx, url, token, workerToken, privKey, pubKey, fp)

	// ── Run (with auto-reconnect backoff) ────────────────────────────────
	slog.Info("Starting connection loop...")
	slog.Info("Ready. Waiting for enrollment...")
	wc.RunWithBackoff()

	slog.Info("Worker shut down complete.")
}
