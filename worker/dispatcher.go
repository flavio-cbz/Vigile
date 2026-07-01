package main

import (
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
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
		log.Printf("SECURITY: action %q is not in whitelist", msg.Action)
		return mustJSON(IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not allowed", msg.Action),
		})
	}

	log.Printf("Dispatching intent: action=%s id=%s requested_by=%s", msg.Action, msg.IntentID, msg.RequestedBy)

	var result IntentResult
	switch msg.Action {
	case "GET_STATS":
		result = handleGetStats(msg)
	case "READ_LOGS":
		result = handleReadLogs(msg)
	case "LIST_CONTAINERS":
		result = handleListContainers(msg)
	case "RESTART_CONTAINER":
		result = handleRestartContainer(msg)
	case "LIST_SERVICES":
		result = handleListServices(msg)
	case "STATUS_SERVICE":
		result = handleStatusService(msg)
	case "RESTART_SERVICE":
		result = handleRestartService(msg)
	case "READ_LOGS_SERVICE":
		result = handleReadLogsService(msg)
	case "UPDATE_WORKER":
		result = handleUpdateWorker(wc, msg)
	default:
		result = IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not implemented", msg.Action),
		}
	}

	result.IntentID = msg.IntentID
	log.Printf("Intent result: id=%s success=%v", result.IntentID, result.Success)
	return mustJSON(result)
}

func handleUpdateWorker(wc *WorkerConn, msg Intent) IntentResult {
	// 1. Determine URLs
	binaryURL := wc.masterURL + fmt.Sprintf("/api/nodes/binary/%s/%s/worker", runtime.GOOS, runtime.GOARCH)
	checksumURL := binaryURL + ".sha256"

	log.Printf("Starting self-update. Downloading from: %s", binaryURL)

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
	resp, err := client.Get(checksumURL)
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
	execDir := filepath.Dir(execPath)
	tmpFile, err := os.CreateTemp(execDir, "vigile-worker-new-*")
	if err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to create temporary file: %v", err)}
	}
	tmpPath := tmpFile.Name()
	defer func() {
		tmpFile.Close()
		os.Remove(tmpPath) // cleaned up if not renamed
	}()

	resp, err = client.Get(binaryURL)
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

	// 6. Perform the atomic swap
	backupPath := execPath + ".old"
	_ = os.Remove(backupPath) // remove old backup if exists
	if err := os.Rename(execPath, backupPath); err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to backup current executable: %v", err)}
	}
	if err := os.Rename(tmpPath, execPath); err != nil {
		// attempt rollback
		_ = os.Rename(backupPath, execPath)
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to replace executable: %v", err)}
	}

	if err := os.Chmod(execPath, 0755); err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("failed to set executable permissions: %v", err)}
	}

	log.Printf("Self-update succeeded. Restart scheduled in 1 second...")

	// 7. Schedule exit after sending result
	go func() {
		time.Sleep(1 * time.Second)
		os.Exit(0)
	}()

	return IntentResult{Success: true, Output: "worker successfully updated, restarting now"}
}

func mustJSON(v interface{}) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		log.Panicf("json marshal failed: %v", err)
	}
	return data
}
