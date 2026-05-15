// YouCloud AI Admin — Worker Node
//
// Autonomous agent that connects to the Master via WebSocket,
// authenticates with Ed25519, and executes whitelisted actions.
//
// Zero external dependencies — stdlib Go only.
//
// Usage:
//
//	youcloud-worker --master http://master:8000 --token <JOIN_TOKEN>
//
// Or use persisted config:
//
//	/etc/youcloud/master_url
//	/etc/youcloud/enrollment.token
package main

import (
	"flag"
	"log"
	"os"
	"os/signal"
	"syscall"
)

// Logger for structured output (stdout for journald collection).
var logger = log.New(os.Stdout, "[youcloud-worker] ", log.Ldate|log.Ltime|log.Lmsgprefix)

func main() {
	// ── CLI flags ────────────────────────────────────────────────────────
	masterURL := flag.String("master", "", "Master WebSocket URL (e.g. http://master:8000)")
	joinToken := flag.String("token", "", "JOIN_TOKEN for enrollment")
	flag.Parse()

	// ── Resolve master URL ───────────────────────────────────────────────
	url := getMasterURL(*masterURL)
	if url == "" {
		logger.Fatal("MASTER_URL is required. Set --master flag or write to /etc/youcloud/master_url")
	}
	// Normalize: ensure http:// scheme for WebSocket upgrade
	if url[:4] != "http" {
		if url[:3] == "wss" {
			url = "https" + url[3:]
		} else if url[:2] == "ws" {
			url = "http" + url[2:]
		} else {
			url = "http://" + url
		}
	}

	logger.Printf("YouCloud Worker starting")
	logger.Printf("Master URL: %s", url)

	// ── Resolve join token ───────────────────────────────────────────────
	token, err := readJoinToken(*joinToken)
	if err != nil {
		logger.Fatalf("Failed to read JOIN_TOKEN: %v", err)
	}
	logger.Printf("JOIN_TOKEN hash: %s", computeTokenHash(token))

	// ── Load or generate Ed25519 keypair ─────────────────────────────────
	privKey, pubKey, err := loadOrGenerateKeypair()
	if err != nil {
		logger.Fatalf("Failed to load/generate keypair: %v", err)
	}
	logger.Printf("Ed25519 public key loaded (%d bytes)", len(pubKey))

	// ── Collect fingerprint ──────────────────────────────────────────────
	fp := collectFingerprint()
	logger.Printf("Fingerprint: hostname=%s arch=%s os=%s", fp.Hostname, fp.Arch, fp.OS)

	// ── Create worker connection ─────────────────────────────────────────
	wc := NewWorkerConn(url, token, privKey, pubKey, fp)

	// ── Handle OS signals ────────────────────────────────────────────────
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigCh
		logger.Printf("Received signal %v, shutting down...", sig)
		wc.Stop()
	}()

	// ── Run (with auto-reconnect backoff) ────────────────────────────────
	logger.Printf("Starting connection loop...")
	logger.Printf("Ready. Waiting for enrollment...")
	wc.RunWithBackoff()

	logger.Printf("Worker shut down complete.")
}
