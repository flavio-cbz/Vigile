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
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
)

// Logger for structured output (stdout for journald collection).
var logger = log.New(os.Stdout, "[vigile-worker] ", log.Ldate|log.Ltime|log.Lmsgprefix)

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
		logger.Fatal("MASTER_URL is required. Set --master flag or write to /etc/vigile/master_url")
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
		logger.Fatal("FATAL: Unencrypted connection (HTTP/WS) is forbidden by default. Set ALLOW_INSECURE=true to bypass.")
	}

	logger.Printf("Vigile Worker starting")
	if allowInsecure {
		logger.Printf("⚠️  WARNING: ALLOW_INSECURE=true is set. Traffic to the Master will not be encrypted. DO NOT USE IN PRODUCTION!")
	} else {
		logger.Printf("🔒 Secure transport enforced (HTTPS/WSS)")
	}
	logger.Printf("Master URL: %s", url)

	// ── Load worker token from disk (for reconnection) ───────────────────
	workerToken, err := readWorkerToken()
	if err != nil {
		logger.Printf("Warning: failed to read worker token: %v", err)
	}
	if workerToken != "" {
		logger.Printf("Worker token loaded from disk — reconnecting with existing identity")
	}

	// ── Resolve join token (not required if worker token exists) ────────
	token, err := readJoinToken(*joinToken)
	if err != nil {
		if workerToken != "" {
			logger.Printf("No JOIN_TOKEN (already consumed) — using worker token for reconnect")
			token = ""
		} else {
			logger.Fatalf("Failed to read JOIN_TOKEN: %v", err)
		}
	}
	if token != "" {
		logger.Printf("JOIN_TOKEN hash: %s", computeTokenHash(token))
	}

	// ── Load or generate Ed25519 keypair ─────────────────────────────────
	privKey, pubKey, err := loadOrGenerateKeypair()
	if err != nil {
		logger.Fatalf("Failed to load/generate keypair: %v", err)
	}
	logger.Printf("Ed25519 public key loaded (%d bytes)", len(pubKey))

	// ── Collect fingerprint ──────────────────────────────────────────────
	fp := collectFingerprint()
	logger.Printf("Fingerprint: hostname=%s arch=%s os=%s", fp.Hostname, fp.Arch, fp.OS)

	// ── Create lifecycle context (cancelled on SIGINT/SIGTERM) ───────────
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		defer func() {
			if r := recover(); r != nil {
				logger.Printf("PANIC in signal handler: %v", r)
			}
		}()
		sig := <-sigCh
		logger.Printf("Received signal %v, shutting down...", sig)
		cancel()
	}()

	// ── Create worker connection ─────────────────────────────────────────
	wc := NewWorkerConn(ctx, url, token, workerToken, privKey, pubKey, fp)

	// ── Run (with auto-reconnect backoff) ────────────────────────────────
	logger.Printf("Starting connection loop...")
	logger.Printf("Ready. Waiting for enrollment...")
	wc.RunWithBackoff()

	logger.Printf("Worker shut down complete.")
}
