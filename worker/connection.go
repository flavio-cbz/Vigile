package main

import (
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net"
	"sync"
	"time"
)

const (
	stateDisconnected = iota
	stateConnecting
	stateOperational
)

const (
	heartbeatInterval    = 30 * time.Second
	heartbeatTimeout     = 90 * time.Second // 3x heartbeat interval
	statusReportInterval = 60 * time.Second
	maxBackoff           = 5 * time.Minute
	initialBackoff       = 1 * time.Second
)

// WorkerConn manages the WebSocket connection lifecycle.
type WorkerConn struct {
	mu          sync.Mutex
	state       int
	nodeID      string
	ws          *WSConn
	masterURL   string
	joinToken   string
	privKey     ed25519.PrivateKey
	pubKey      ed25519.PublicKey
	fingerprint Fingerprint
	workerToken string

	stopCh chan struct{}
	doneCh chan struct{}
}

// workerToken is an optional persisted token for reconnection (empty on first enrollment).
func NewWorkerConn(masterURL, joinToken, workerToken string, privKey ed25519.PrivateKey, pubKey ed25519.PublicKey, fp Fingerprint) *WorkerConn {
	return &WorkerConn{
		masterURL:   masterURL,
		joinToken:   joinToken,
		workerToken: workerToken,
		privKey:     privKey,
		pubKey:      pubKey,
		fingerprint: fp,
		stopCh:      make(chan struct{}),
		doneCh:      make(chan struct{}),
	}
}

// Connect establishes the WebSocket connection and runs the enrollment handshake.
func (wc *WorkerConn) Connect() error {
	wc.mu.Lock()
	if wc.state == stateOperational {
		wc.mu.Unlock()
		return fmt.Errorf("already connected")
	}
	wc.state = stateConnecting
	wc.mu.Unlock()

	// Dial WebSocket
	wsURL := wc.masterURL + "/ws/worker/join"
	logger.Printf("Connecting to %s ...", wsURL)

	ws, err := DialWebSocket(wsURL)
	if err != nil {
		wc.mu.Lock()
		wc.state = stateDisconnected
		wc.mu.Unlock()
		return fmt.Errorf("dial: %w", err)
	}
	logger.Printf("WebSocket connected")

	wc.ws = ws

	// Phase 1: Enrollment
	if err := wc.runEnrollment(); err != nil {
		ws.Close()
		wc.mu.Lock()
		wc.state = stateDisconnected
		wc.mu.Unlock()
		return fmt.Errorf("enrollment: %w", err)
	}

	logger.Printf("Enrolled as node %s", wc.nodeID)
	return nil
}

// runEnrollment performs the Ed25519 challenge/response handshake.
// When workerToken is set (reconnect mode), the challenge is skipped
// and the worker token is used for authentication instead.
func (wc *WorkerConn) runEnrollment() error {
	// 1. Send ENROLLMENT_REQUEST (with worker_token if reconnecting)
	req := buildEnrollmentRequest(wc.joinToken, wc.workerToken, wc.pubKey, wc.fingerprint)
	logger.Printf("ENROLL: sending request (token_len=%d, pubkey_len=%d, reconnect=%v)",
		len(wc.joinToken), len(b64enc.EncodeToString(wc.pubKey)), wc.workerToken != "")
	if err := wc.sendJSON(req); err != nil {
		return fmt.Errorf("send request: %w", err)
	}

	// Reconnect mode: master skips the Ed25519 challenge and sends SUCCESS directly
	if wc.workerToken != "" {
		logger.Printf("ENROLL: reconnect mode — waiting for ENROLLMENT_SUCCESS (skip challenge)")
		success, err := wc.readTyped("ENROLLMENT_SUCCESS")
		if err != nil {
			return fmt.Errorf("read success (reconnect): %w", err)
		}
		return wc.handleSuccessMessage(success, "reconnect")
	}

	// 2. Receive ENROLLMENT_CHALLENGE (first-time enrollment only)
	challengeMsg, err := wc.readTyped("ENROLLMENT_CHALLENGE")
	if err != nil {
		return fmt.Errorf("read challenge: %w", err)
	}
	challenge, _ := challengeMsg["challenge"].(string)
	if challenge == "" {
		return fmt.Errorf("empty challenge")
	}
	logger.Printf("ENROLL: got challenge (%d bytes): %s", len(challenge), challenge)

	// 3. Decode challenge from base64, sign the RAW bytes, encode back
	challengeRaw, err := b64enc.DecodeString(challenge)
	if err != nil {
		return fmt.Errorf("decode challenge: %w", err)
	}
	sig := ed25519.Sign(wc.privKey, challengeRaw)
	sigB64 := b64enc.EncodeToString(sig)
	resp := map[string]interface{}{
		"type":      "ENROLLMENT_RESPONSE",
		"signature": sigB64,
	}
	logger.Printf("ENROLL: signed challenge (%d raw bytes), sig=%s...", len(challengeRaw), sigB64[:20])
	if err := wc.sendJSON(resp); err != nil {
		return fmt.Errorf("send response: %w", err)
	}

	// 4. Receive ENROLLMENT_SUCCESS
	success, err := wc.readTyped("ENROLLMENT_SUCCESS")
	if err != nil {
		return fmt.Errorf("read success: %w", err)
	}

	return wc.handleSuccessMessage(success, "enroll")
}

func (wc *WorkerConn) handleSuccessMessage(success map[string]interface{}, mode string) error {
	wc.workerToken, _ = success["worker_token"].(string)
	wc.nodeID, _ = success["node_id"].(string)

	if wc.nodeID == "" {
		return fmt.Errorf("no node_id in success message (%s)", mode)
	}

	// Persist the worker token for future reconnections
	if wc.workerToken != "" {
		if err := persistWorkerToken(wc.workerToken); err != nil {
			logger.Printf("Warning: failed to persist worker token (%s): %v", mode, err)
		}
	}
	nodeID = wc.nodeID

	logger.Printf("ENROLL: %s success! node_id=%s", mode, wc.nodeID)
	return nil
}

// RunOperational enters the operational phase: heartbeat + status + intent dispatch.
func (wc *WorkerConn) RunOperational() error {
	wc.mu.Lock()
	ws := wc.ws
	if ws == nil {
		wc.mu.Unlock()
		return errors.New("websocket not connected")
	}
	wc.state = stateOperational
	wc.mu.Unlock()

	logger.Printf("Operational phase started (node=%s)", wc.nodeID)

	heartbeatTicker := time.NewTicker(heartbeatInterval)
	defer heartbeatTicker.Stop()

	statusTicker := time.NewTicker(statusReportInterval)
	defer statusTicker.Stop()

	// Dedicated goroutine for reading WebSocket messages.
	// Uses a 90s read deadline as safety net if Master goes silent.
	type wsMsg struct {
		data []byte
		err  error
	}
	msgCh := make(chan wsMsg, 1)
	go func() {
		for {
			_ = ws.SetReadDeadline(time.Now().Add(90 * time.Second))
			data, err := ws.ReadText()
			select {
			case msgCh <- wsMsg{data, err}:
			default:
				// Channel full (shouldn't happen), drop message
			}
			if err != nil {
				return
			}
		}
	}()

	for {
		select {
		case <-wc.stopCh:
			logger.Printf("Stop signal received")
			return nil

		case <-heartbeatTicker.C:
			if err := wc.sendJSON(map[string]interface{}{
				"type": "HEARTBEAT",
				"ts":   float64(time.Now().UnixMicro()) / 1_000_000,
			}); err != nil {
				return fmt.Errorf("heartbeat send: %w", err)
			}

		case <-statusTicker.C:
			report := buildStatusReport()
			if err := wc.sendJSON(report); err != nil {
				logger.Printf("Status report error: %v", err)
			}

		case msg := <-msgCh:
			if msg.err != nil {
				// Check for heartbeat timeout using errors.As
				// (errors are wrapped by readFrame → fmt.Errorf, so
				// direct type assertion on net.Error would fail)
				var netErr net.Error
				if errors.As(msg.err, &netErr) && netErr.Timeout() {
					return fmt.Errorf("read timeout: %w", netErr)
				}
				return fmt.Errorf("read error: %w", msg.err)
			}

			var msgObj map[string]interface{}
			if err := json.Unmarshal(msg.data, &msgObj); err != nil {
				logger.Printf("Invalid JSON from master: %v", err)
				continue
			}

			msgType, _ := msgObj["type"].(string)

			switch msgType {
			case "HEARTBEAT_ACK":
				// Heartbeat acknowledged by Master

			case "INTENT":
				result := dispatchIntent(msg.data)
				var resObj map[string]interface{}
				if err := json.Unmarshal(result, &resObj); err != nil {
					logger.Printf("Failed to parse intent result: %v", err)
					continue
				}
				resObj["type"] = "INTENT_RESULT"
				if err := wc.sendJSON(resObj); err != nil {
					logger.Printf("Failed to send INTENT_RESULT: %v", err)
				}

			default:
				logger.Printf("Unknown message type: %s", msgType)
			}
		}
	}
}

// RunWithBackoff connects and runs with exponential backoff.
// After successful enrollment, disconnection triggers automatic reconnect
// using the persisted worker_token. Falls back to clean exit if no token.
func (wc *WorkerConn) RunWithBackoff() {
	backoff := initialBackoff
	enrolled := false

	for {
		select {
		case <-wc.stopCh:
			wc.disconnect()
			logger.Printf("Worker stopped gracefully")
			close(wc.doneCh)
			return
		default:
		}

		if !enrolled {
			logger.Printf("Connecting (backoff=%v)...", backoff)
		}

		if err := wc.Connect(); err != nil {
			if enrolled {
				logger.Printf("Reconnect failed: %v", err)
				// If we have a worker token and still fail, keep retrying
				if wc.workerToken != "" {
					logger.Printf("Worker token present — will retry reconnect")
				} else {
					logger.Printf("No worker token — giving up")
					wc.disconnect()
					close(wc.doneCh)
					return
				}
			} else {
				logger.Printf("Connection failed: %v — retry in %v", err, backoff)
			}
			wc.disconnect()

			select {
			case <-wc.stopCh:
				logger.Printf("Stopped during backoff")
				close(wc.doneCh)
				return
			case <-time.After(backoff):
			}

			backoff = time.Duration(math.Min(
				float64(backoff)*2,
				float64(maxBackoff),
			))
			continue
		}

		// Connected!
		enrolled = true
		backoff = initialBackoff

		logger.Printf("Enrolled as node %s — entering operational phase", wc.nodeID)
		if err := wc.RunOperational(); err != nil {
			logger.Printf("Operational ended: %v", err)
		}

		// Disconnected — try to reconnect with persisted worker token
		wc.disconnect()

		// Load worker token for reconnection (if not already set)
		if wc.workerToken == "" {
			wt, err := readWorkerToken()
			if err != nil {
				logger.Printf("Cannot read worker token: %v — exiting", err)
				close(wc.doneCh)
				return
			}
			if wt == "" {
				logger.Printf("No worker token available — JOIN_TOKEN consumed, exiting")
				close(wc.doneCh)
				return
			}
			wc.mu.Lock()
			wc.workerToken = wt
			wc.mu.Unlock()
		}

		logger.Printf("Reconnecting with persisted worker token...")
		_ = backoff // Reset backoff for reconnect attempts
		backoff = initialBackoff
		continue
	}
}

// Stop signals graceful shutdown.
func (wc *WorkerConn) Stop() {
	select {
	case <-wc.stopCh:
	default:
		close(wc.stopCh)
	}
}

// Wait blocks until the worker has fully stopped.
func (wc *WorkerConn) Wait() {
	<-wc.doneCh
}

func (wc *WorkerConn) disconnect() {
	wc.mu.Lock()
	defer wc.mu.Unlock()
	if wc.ws != nil {
		wc.ws.Close()
		wc.ws = nil
	}
	wc.state = stateDisconnected
}

// ── Helpers ────────────────────────────────────────────────────────────────

func (wc *WorkerConn) sendJSON(data interface{}) error {
	msg, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("json marshal: %w", err)
	}
	wc.mu.Lock()
	ws := wc.ws
	wc.mu.Unlock()
	if ws == nil {
		return errors.New("websocket not connected")
	}
	return ws.WriteText(msg)
}

func (wc *WorkerConn) readTyped(expectedType string) (map[string]interface{}, error) {
	wc.mu.Lock()
	ws := wc.ws
	wc.mu.Unlock()
	if ws == nil {
		return nil, errors.New("websocket not connected")
	}
	data, err := ws.ReadText()
	if err != nil {
		return nil, err
	}
	var msg map[string]interface{}
	if err := json.Unmarshal(data, &msg); err != nil {
		return nil, fmt.Errorf("json parse: %w", err)
	}
	gotType, _ := msg["type"].(string)
	if gotType != expectedType {
		return nil, fmt.Errorf("expected type %q, got %q", expectedType, gotType)
	}
	return msg, nil
}

// Param helpers used by action handlers.
func getParamString(params map[string]interface{}, key, defaultVal string) string {
	if params == nil {
		return defaultVal
	}
	if v, ok := params[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return defaultVal
}

func getParamInt(params map[string]interface{}, key string, defaultVal int) int {
	if params == nil {
		return defaultVal
	}
	if v, ok := params[key]; ok {
		switch n := v.(type) {
		case float64:
			return int(n)
		case int:
			return n
		case int64:
			return int(n)
		}
	}
	return defaultVal
}
