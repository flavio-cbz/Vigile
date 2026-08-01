package main

import (
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"runtime"
	"strings"
	"time"
)

// nodeID is set during enrollment and used for enrichment in action logs.
var nodeID string

// ALLOWED_ACTIONS is the hardcoded whitelist of actions this Worker can execute.
// Every incoming INTENT is checked against this map before execution.
var ALLOWED_ACTIONS = map[string]bool{
		"GET_STATS":         true,
		"READ_LOGS":         true,
		"RESTART_CONTAINER": true,
		"LIST_CONTAINERS":   true,
		"LIST_SERVICES":     true,
		"STATUS_SERVICE":    true,
		"RESTART_SERVICE":   true,
		"READ_LOGS_SERVICE": true,
		"UPDATE_WORKER":     true,
		"TOKEN_ROTATION":    true,
		"DISK_SCAN":         true,
	}

// Intent describes a command sent by the Master.
type Intent struct {
	IntentID    string                 `json:"intent_id"`
	Action      string                 `json:"action"`
	Params      map[string]interface{} `json:"params,omitempty"`
	RequestedBy string                 `json:"requested_by,omitempty"`
}

// IntentResult is sent back to the Master after execution.
type IntentResult struct {
	IntentID string `json:"intent_id"`
	Success  bool   `json:"success"`
	Output   string `json:"output,omitempty"`
	Error    string `json:"error,omitempty"`
}

// dispatchIntent validates and executes an incoming intent.
func dispatchIntent(wc *WorkerConn, raw []byte) []byte {
	var msg Intent
	if err := json.Unmarshal(raw, &msg); err != nil {
		return mustJSON(IntentResult{Error: fmt.Sprintf("invalid JSON: %v", err)})
	}

	// Whitelist check
	if !ALLOWED_ACTIONS[msg.Action] {
		slog.Warn("security: action not in whitelist", "action", msg.Action)
		return mustJSON(IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not allowed", msg.Action),
		})
	}

	slog.Info("dispatching intent", "action", msg.Action, "id", msg.IntentID, "requested_by", msg.RequestedBy)

	var result IntentResult
	switch msg.Action {
	case "GET_STATS":
		result = handleGetStats(wc.ctx, msg)
	case "READ_LOGS":
		result = handleReadLogs(wc.ctx, msg)
	case "LIST_CONTAINERS":
		result = handleListContainers(wc.ctx, msg)
	case "RESTART_CONTAINER":
		result = handleRestartContainer(wc.ctx, msg)
	case "LIST_SERVICES":
		result = handleListServices(wc.ctx, msg)
	case "STATUS_SERVICE":
		result = handleStatusService(wc.ctx, msg)
	case "RESTART_SERVICE":
		result = handleRestartService(wc.ctx, msg)
	case "READ_LOGS_SERVICE":
		result = handleReadLogsService(wc.ctx, msg)
	case "UPDATE_WORKER":
		result = handleUpdateWorker(wc.ctx, wc, msg)
	case "TOKEN_ROTATION":
		result = handleTokenRotation(wc.ctx, wc, msg)
	case "DISK_SCAN":
		result = handleDiskScan(wc.ctx, msg)
	default:
		result = IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not implemented", msg.Action),
		}
	}

	result.IntentID = msg.IntentID
	slog.Info("intent result", "id", result.IntentID, "success", result.Success)
	return mustJSON(result)
}

func handleUpdateWorker(ctx context.Context, wc *WorkerConn, msg Intent) IntentResult {
	// 1. Determine URLs
	binaryURL := wc.masterURL + fmt.Sprintf("/api/nodes/binary/%s/%s/worker", runtime.GOOS, runtime.GOARCH)
	checksumURL := binaryURL + ".sha256"

	slog.Info("starting self-update", "url", binaryURL)

	// 2. Setup HTTP Client with ALLOW_INSECURE support
	tr := &http.Transport{}
	if os.Getenv("ALLOW_INSECURE") == "true" {
		tr.TLSClientConfig = &tls.Config{InsecureSkipVerify: true}
	}
	client := &http.Client{
		Transport: tr,
		Timeout:   60 * time.Second,
	}

	// 3. Download checksum
	req, err := http.NewRequestWithContext(ctx, "GET", checksumURL, nil)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to create checksum request: %v", err)}
	}
	resp, err := client.Do(req)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to download checksum: %v", err)}
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return IntentResult{Success: false, Error: fmt.Sprintf("checksum download returned status: %d", resp.StatusCode)}
	}
	checksumBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to read checksum: %v", err)}
	}
	expectedHash := strings.TrimSpace(strings.Split(string(checksumBytes), " ")[0])
	if len(expectedHash) != 64 {
		return IntentResult{Success: false, Error: fmt.Sprintf("invalid checksum format: %q", string(checksumBytes))}
	}

	// 4. Download new binary to temporary file
	execPath, err := os.Executable()
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to locate executable: %v", err)}
	}
	// Try /tmp first (writable tmpfs in most Linux setups + Docker).
	// Fall back to /etc/vigile (ReadWritePaths in systemd unit).
	var tmpFile *os.File
	for _, dir := range []string{"/tmp", "/etc/vigile", ""} {
		tmpFile, err = os.CreateTemp(dir, "vigile-worker-new-*")
		if err == nil {
			break
		}
	}
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to create temporary file (tried /tmp, /etc/vigile, and os.TempDir): %v", err)}
	}
	tmpPath := tmpFile.Name()
	defer func() {
		tmpFile.Close()
		os.Remove(tmpPath)
	}()

	reqBin, err := http.NewRequestWithContext(ctx, "GET", binaryURL, nil)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to create binary request: %v", err)}
	}
	resp, err = client.Do(reqBin)
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to download binary: %v", err)}
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return IntentResult{Success: false, Error: fmt.Sprintf("binary download returned status: %d", resp.StatusCode)}
	}

	hasher := sha256.New()
	writer := io.MultiWriter(tmpFile, hasher)
	if _, err := io.Copy(writer, resp.Body); err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to write binary: %v", err)}
	}
	tmpFile.Close()

	// 5. Verify checksum
	actualHash := hex.EncodeToString(hasher.Sum(nil))
	if actualHash != expectedHash {
		return IntentResult{Success: false, Error: fmt.Sprintf("checksum mismatch: expected %s, got %s", expectedHash, actualHash)}
	}

	// 6. Back up the current binary (best-effort — read-only fs like Docker
	//    containers skip gracefully and fall through to the replacement step).
	backupPath := execPath + ".old"
	_ = os.Remove(backupPath)
	backupOK := true
	if err := os.Rename(execPath, backupPath); err != nil {
		slog.Warn("backup rename failed (proceeding without backup)", "error", err)
		backupOK = false
	}

	// 7. Swap — try atomic rename first, fall back to copy+remove
	//     (temp file is in /tmp, which may be a different filesystem).
	replaceErr := os.Rename(tmpPath, execPath)
	if replaceErr != nil {
		// Cross-device or other: copy instead
		var copyErr error
		var data []byte
		data, copyErr = os.ReadFile(tmpPath)
		if copyErr == nil {
			copyErr = os.WriteFile(execPath, data, 0755)
		}
		if copyErr != nil {
			if backupOK {
				_ = os.Rename(backupPath, execPath) // rollback only when we have a backup
			}
			return IntentResult{Success: false, Error: fmt.Sprintf("failed to replace executable: %v", copyErr)}
		}
		_ = os.Remove(tmpPath)
	} else {
		if err := os.Chmod(execPath, 0755); err != nil {
			return IntentResult{Success: false, Error: fmt.Sprintf("failed to set executable permissions: %v", err)}
		}
	}

	slog.Info("self-update succeeded — restart scheduled")

	// 7. Schedule exit after sending result
	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("PANIC in restart goroutine", "recover", r)
			}
		}()
		select {
		case <-time.After(1 * time.Second):
		case <-wc.ctx.Done():
		}
		os.Exit(0)
	}()

	return IntentResult{Success: true, Output: "worker successfully updated, restarting now"}
}

func handleTokenRotation(ctx context.Context, wc *WorkerConn, msg Intent) IntentResult {
	// Extract worker_token from params
	newToken, ok := msg.Params["worker_token"].(string)
	if !ok || newToken == "" {
		return IntentResult{Success: false, Error: "missing or empty worker_token in params"}
	}

	// Persist the new token
	if err := persistWorkerToken(newToken); err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to persist worker token: %v", err)}
	}

	// Update the in-memory token
	wc.mu.Lock()
	wc.workerToken = newToken
	wc.mu.Unlock()

	slog.Info("TOKEN_ROTATION: new token received", "len", len(newToken))
	return IntentResult{Success: true, Output: "token rotated"}
}

func mustJSON(v interface{}) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		slog.Error("json marshal failed", "error", err)
		panic(err)
	}
	return data
}
