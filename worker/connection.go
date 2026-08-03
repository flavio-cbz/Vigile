package main

import (
	"context"
	"crypto/ed25519"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"math"
	"net"
	"sync"
	"time"
)

// Connection states.
const (
	stateDisconnected = iota
	stateConnecting
	stateOperational
)

const (
	// heartbeatInterval is how often the worker sends a heartbeat to the master.
	heartbeatInterval = 30 * time.Second
	// heartbeatTimeout is the maximum time to wait for a heartbeat ack before
	// considering the connection dead (3× heartbeatInterval).
	heartbeatTimeout = 90 * time.Second // 3x heartbeat interval
	// statusReportInterval is how often the worker sends a full metrics report.
	statusReportInterval = 60 * time.Second
	// maxBackoff is the ceiling for the exponential reconnect backoff.
	maxBackoff = 5 * time.Minute
	// initialBackoff is the starting delay before the first reconnect attempt.
	initialBackoff = 1 * time.Second
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

	ctx    context.Context
	cancel context.CancelFunc
	stopCh chan struct{}
	doneCh chan struct{}
}

// NewWorkerConn creates a new WorkerConn.
// workerToken is an optional persisted token for reconnection (empty on first enrollment).
// The provided context controls the worker lifecycle; cancelling it triggers graceful shutdown.
func NewWorkerConn(ctx context.Context, masterURL, joinToken, workerToken string, privKey ed25519.PrivateKey, pubKey ed25519.PublicKey, fp Fingerprint) *WorkerConn {
	ctx, cancel := context.WithCancel(ctx)
	wc := &WorkerConn{
		masterURL:   masterURL,
		joinToken:   joinToken,
		workerToken: workerToken,
		privKey:     privKey,
		pubKey:      pubKey,
		fingerprint: fp,
		ctx:         ctx,
		cancel:      cancel,
		stopCh:      make(chan struct{}),
		doneCh:      make(chan struct{}),
	}
	// Propagate context cancellation to stopCh so all goroutines observe shutdown.
	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("PANIC in context propagation goroutine", "recover", r)
			}
		}()
		select {
		case <-ctx.Done():
			wc.Stop()
		case <-wc.stopCh:
		}
	}()
	return wc
}

// Connect establishes the WebSocket connection and runs the enrollment handshake.
func (wc *WorkerConn) Connect(ctx context.Context) error {
	wc.mu.Lock()
	if wc.state == stateOperational {
		wc.mu.Unlock()
		return fmt.Errorf("already connected")
	}
	wc.state = stateConnecting
	wc.mu.Unlock()

	// Dial WebSocket
	wsURL := wc.masterURL + "/ws/worker/join"
	slog.Info("Connecting to master", "url", wsURL)

	ws, err := DialWebSocket(wc.ctx, wsURL)
	if err != nil {
		wc.mu.Lock()
		wc.state = stateDisconnected
		wc.mu.Unlock()
		return fmt.Errorf("dial: %w", err)
	}
	slog.Info("WebSocket connected")

	wc.ws = ws

	// Phase 1: Enrollment
	if err := wc.runEnrollment(ctx); err != nil {
		ws.Close()
		wc.mu.Lock()
		wc.state = stateDisconnected
		wc.mu.Unlock()
		return fmt.Errorf("enrollment: %w", err)
	}

	slog.Info("Enrolled as node", "node_id", wc.nodeID)
	return nil
}

// runEnrollment performs the Ed25519 challenge/response handshake.
// When workerToken is set (reconnect mode), the challenge is skipped
// and the worker token is used for authentication instead.
func (wc *WorkerConn) runEnrollment(ctx context.Context) error {
	// 1. Send ENROLLMENT_REQUEST (with worker_token if reconnecting)
	req := buildEnrollmentRequest(wc.joinToken, wc.workerToken, wc.pubKey, wc.fingerprint)
	slog.Info("ENROLL: sending request",
		"token_len", len(wc.joinToken), "pubkey_len", len(b64enc.EncodeToString(wc.pubKey)), "reconnect", wc.workerToken != "")
	if err := wc.sendJSON(ctx,req); err != nil {
		return fmt.Errorf("send request: %w", err)
	}

	// Reconnect mode: master skips the Ed25519 challenge and sends SUCCESS directly
	if wc.workerToken != "" {
		slog.Info("ENROLL: reconnect mode — waiting for ENROLLMENT_SUCCESS (skip challenge)")
		success, err := wc.readTyped(ctx,"ENROLLMENT_SUCCESS")
		if err != nil {
			return fmt.Errorf("read success (reconnect): %w", err)
		}
		if token, ok := success["worker_token"].(string); ok {
			wc.workerToken = token
		}
		if id, ok := success["node_id"].(string); ok {
			wc.nodeID = id
		}
		if wc.nodeID == "" {
			return fmt.Errorf("no node_id in success message (reconnect)")
		}
		// Persist the refreshed worker token
		if wc.workerToken != "" {
			if err := persistWorkerToken(wc.workerToken); err != nil {
				slog.Warn("failed to persist refreshed worker token", "error", err)
			}
		}
		nodeID = wc.nodeID
		slog.Info("ENROLL: reconnect success", "node_id", wc.nodeID)
		return nil
	}

	// 2. Receive ENROLLMENT_CHALLENGE (first-time enrollment only)
	challengeMsg, err := wc.readTyped(ctx,"ENROLLMENT_CHALLENGE")
	if err != nil {
		return fmt.Errorf("read challenge: %w", err)
	}
	var challenge string
	if chal, ok := challengeMsg["challenge"].(string); ok {
		challenge = chal
	}
	if challenge == "" {
		return fmt.Errorf("empty challenge")
	}
	slog.Info("ENROLL: got challenge", "bytes", len(challenge))

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
	slog.Info("ENROLL: signed challenge", "raw_bytes", len(challengeRaw), "sig_prefix", sigB64[:20])
	if err := wc.sendJSON(ctx,resp); err != nil {
		return fmt.Errorf("send response: %w", err)
	}

	// 4. Receive ENROLLMENT_SUCCESS
	success, err := wc.readTyped(ctx,"ENROLLMENT_SUCCESS")
	if err != nil {
		return fmt.Errorf("read success: %w", err)
	}

	if token, ok := success["worker_token"].(string); ok {
		wc.workerToken = token
	}
	if id, ok := success["node_id"].(string); ok {
		wc.nodeID = id
	}

	if wc.nodeID == "" {
		return fmt.Errorf("no node_id in success message")
	}

	// Persist the worker token for future reconnections
	if wc.workerToken != "" {
		if err := persistWorkerToken(wc.workerToken); err != nil {
			slog.Warn("failed to persist worker token", "error", err)
		}
	}
	nodeID = wc.nodeID

	slog.Info("ENROLL: success", "node_id", wc.nodeID)
	return nil
}

// RunOperational enters the operational phase: heartbeat + status + intent dispatch.
func (wc *WorkerConn) RunOperational(ctx context.Context) error {
	wc.mu.Lock()
	ws := wc.ws
	if ws == nil {
		wc.mu.Unlock()
		return errors.New("websocket not connected")
	}
	wc.state = stateOperational
	wc.mu.Unlock()

	slog.Info("Operational phase started", "node_id", wc.nodeID)

	heartbeatTicker := time.NewTicker(heartbeatInterval)
	defer heartbeatTicker.Stop()

	statusTicker := time.NewTicker(statusReportInterval)
	defer statusTicker.Stop()

	// Send initial status report immediately on connection
	initialReport := buildStatusReport(wc.ctx)
	if err := wc.sendJSON(ctx, initialReport); err != nil {
		slog.Warn("initial status report error", "error", err)
	}

	// Dedicated goroutine for reading WebSocket messages.
	// Uses a 90s read deadline as safety net if Master goes silent.
	type wsMsg struct {
		data []byte
		err  error
	}
	msgCh := make(chan wsMsg, 1)
	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("PANIC in WS read goroutine", "recover", r)
			}
		}()
		for {
			select {
			case <-wc.ctx.Done():
				return
			default:
			}
			_ = ws.SetReadDeadline(time.Now().Add(90 * time.Second))
			data, err := ws.ReadText()
			select {
			case msgCh <- wsMsg{data, err}:
			default:
			}
			if err != nil {
				return
			}
		}
	}()

	for {
		select {
		case <-wc.stopCh:
			slog.Info("stop signal received")
			return nil

		case <-wc.ctx.Done():
			slog.Info("context cancelled, stopping operational phase")
			return nil

		case <-heartbeatTicker.C:
			if err := wc.sendJSON(ctx,map[string]interface{}{
				"type":    "HEARTBEAT",
				"ts":      float64(time.Now().UnixMicro()) / 1_000_000,
				"version": Version,
			}); err != nil {
				return fmt.Errorf("heartbeat send: %w", err)
			}

		case <-statusTicker.C:
			report := buildStatusReport(wc.ctx)
			if err := wc.sendJSON(ctx,report); err != nil {
				slog.Warn("status report error", "error", err)
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
				slog.Warn("invalid JSON from master", "error", err)
				continue
			}

			msgType, ok := msgObj["type"].(string)
			if !ok {
				slog.Warn("message from master missing type field")
				continue
			}

			switch msgType {
			case "HEARTBEAT_ACK":
				// Heartbeat acknowledged by Master

			case "INTENT":
				result := dispatchIntent(wc, msg.data)
				var resObj map[string]interface{}
				if err := json.Unmarshal(result, &resObj); err != nil {
					slog.Warn("failed to parse intent result", "error", err)
					continue
				}
				resObj["type"] = "INTENT_RESULT"
				if err := wc.sendJSON(ctx,resObj); err != nil {
					slog.Warn("failed to send INTENT_RESULT", "error", err)
				}

			case "TOKEN_ROTATION_COMMAND":
				newToken, ok := msgObj["worker_token"].(string)
				if !ok || newToken == "" {
					slog.Warn("TOKEN_ROTATION: missing worker_token in command")
					continue
				}
				wc.mu.Lock()
				wc.workerToken = newToken
				wc.mu.Unlock()
				if err := persistWorkerToken(newToken); err != nil {
					slog.Warn("failed to persist rotated token", "error", err)
				}
				if err := wc.sendJSON(ctx,map[string]interface{}{
					"type": "TOKEN_ROTATION_ACK",
				}); err != nil {
					slog.Warn("failed to send TOKEN_ROTATION_ACK", "error", err)
				}
				slog.Info("TOKEN_ROTATION: worker token rotated successfully")

			default:
				slog.Warn("unknown message type", "type", msgType)
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
			slog.Info("Worker stopped gracefully")
			close(wc.doneCh)
			return
		case <-wc.ctx.Done():
			slog.Info("context cancelled, stopping worker")
			wc.disconnect()
			close(wc.doneCh)
			return
		default:
		}

		if !enrolled {
			slog.Info("connecting (backoff)", "backoff", backoff)
		}

		if err := wc.Connect(wc.ctx); err != nil {
			if enrolled {
				slog.Warn("reconnect failed", "error", err)
				// If we have a worker token and still fail, keep retrying
				if wc.workerToken != "" {
					slog.Info("worker token present — will retry reconnect")
				} else {
					slog.Warn("no worker token — giving up")
					wc.disconnect()
					close(wc.doneCh)
					return
				}
			} else {
				slog.Warn("connection failed", "error", err, "retry_in", backoff)
			}
			wc.disconnect()

		select {
		case <-wc.stopCh:
			slog.Info("stopped during backoff")
			close(wc.doneCh)
			return
		case <-wc.ctx.Done():
			slog.Info("context cancelled during backoff")
			wc.disconnect()
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

		slog.Info("enrolled — entering operational phase", "node_id", wc.nodeID)
		if err := wc.RunOperational(wc.ctx); err != nil {
			slog.Error("operational ended", "error", err)
		}

		// Disconnected — try to reconnect with persisted worker token
		wc.disconnect()

		// Load worker token for reconnection (if not already set)
		if wc.workerToken == "" {
			wt, err := readWorkerToken()
			if err != nil {
				slog.Warn("cannot read worker token — exiting", "error", err)
				close(wc.doneCh)
				return
			}
			if wt == "" {
				slog.Warn("no worker token available — JOIN_TOKEN consumed, exiting")
				close(wc.doneCh)
				return
			}
			wc.mu.Lock()
			wc.workerToken = wt
			wc.mu.Unlock()
		}

		slog.Info("reconnecting with persisted worker token")
		_ = backoff // Reset backoff for reconnect attempts
		backoff = initialBackoff
		continue
	}
}

// Stop signals graceful shutdown.
func (wc *WorkerConn) Stop() {
	wc.cancel()
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

func (wc *WorkerConn) sendJSON(ctx context.Context, data interface{}) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}
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

func (wc *WorkerConn) readTyped(ctx context.Context, expectedType string) (map[string]interface{}, error) {
	select {
	case <-ctx.Done():
		return nil, ctx.Err()
	default:
	}
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
	gotType, ok := msg["type"].(string)
	if !ok {
		return nil, fmt.Errorf("message missing 'type' field, expected %q", expectedType)
	}
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
