package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPersistAndReadWorkerToken(t *testing.T) {
	tmpDir := t.TempDir()
	origKeyDir := keyDir
	origTokenPath := workerTokenPath
	keyDir = tmpDir
	workerTokenPath = filepath.Join(tmpDir, "worker_token")
	defer func() {
		keyDir = origKeyDir
		workerTokenPath = origTokenPath
	}()

	// Persist a token
	token := "test-worker-token-value"
	if err := persistWorkerToken(token); err != nil {
		t.Fatalf("persistWorkerToken failed: %v", err)
	}

	// Verify file exists at correct path
	if _, err := os.Stat(workerTokenPath); os.IsNotExist(err) {
		t.Fatalf("worker_token file not created at %s", workerTokenPath)
	}

	// Verify file permissions (mode 0600)
	info, err := os.Stat(workerTokenPath)
	if err != nil {
		t.Fatalf("stat failed: %v", err)
	}
	perm := info.Mode().Perm()
	if perm != 0600 {
		t.Fatalf("expected permissions 0600, got %o", perm)
	}

	// Read it back
	readToken, err := readWorkerToken()
	if err != nil {
		t.Fatalf("readWorkerToken failed: %v", err)
	}
	if readToken != token {
		t.Fatalf("readWorkerToken: got %q, want %q", readToken, token)
	}
}

func TestReadWorkerTokenFileNotExist(t *testing.T) {
	tmpDir := t.TempDir()
	origTokenPath := workerTokenPath
	workerTokenPath = filepath.Join(tmpDir, "nonexistent_worker_token")
	defer func() {
		workerTokenPath = origTokenPath
	}()

	token, err := readWorkerToken()
	if err != nil {
		t.Fatalf("readWorkerToken on non-existent file should not error: %v", err)
	}
	if token != "" {
		t.Fatalf("expected empty token for non-existent file, got %q", token)
	}
}

func TestPersistEmptyWorkerToken(t *testing.T) {
	tmpDir := t.TempDir()
	origTokenPath := workerTokenPath
	workerTokenPath = filepath.Join(tmpDir, "worker_token")
	defer func() {
		workerTokenPath = origTokenPath
	}()

	err := persistWorkerToken("")
	if err == nil {
		t.Fatal("persistWorkerToken with empty token should error")
	}
	if !strings.Contains(err.Error(), "empty") {
		t.Fatalf("error should mention empty token, got: %v", err)
	}
}

func TestBuildEnrollmentRequestReconnect(t *testing.T) {
	pub := make([]byte, 32)
	fp := Fingerprint{Hostname: "reconnect-test", MachineID: "abc123", Arch: "x86_64", OS: "linux"}

	// Reconnect mode: workerToken provided, joinToken empty
	req := buildEnrollmentRequest("", "worker-token-abc", pub, fp)

	if req["type"] != "ENROLLMENT_REQUEST" {
		t.Fatalf("expected type ENROLLMENT_REQUEST, got %v", req["type"])
	}
	if req["join_token"] != "" {
		t.Fatalf("expected join_token to be empty in reconnect mode, got %v", req["join_token"])
	}
	wt, ok := req["worker_token"].(string)
	if !ok || wt != "worker-token-abc" {
		t.Fatalf("expected worker_token 'worker-token-abc', got %v", req["worker_token"])
	}
	reconnect, ok := req["reconnect"].(bool)
	if !ok || !reconnect {
		t.Fatalf("expected reconnect=true, got %v", req["reconnect"])
	}
}

func TestBuildEnrollmentRequestFirstEnrollment(t *testing.T) {
	pub := make([]byte, 32)
	fp := Fingerprint{Hostname: "first-enroll", MachineID: "def456", Arch: "arm64", OS: "linux"}

	// First enrollment: joinToken provided, workerToken empty
	req := buildEnrollmentRequest("join-token-xyz", "", pub, fp)

	if req["type"] != "ENROLLMENT_REQUEST" {
		t.Fatalf("expected type ENROLLMENT_REQUEST, got %v", req["type"])
	}
	if req["join_token"] != "join-token-xyz" {
		t.Fatalf("expected join_token 'join-token-xyz', got %v", req["join_token"])
	}
	if _, exists := req["worker_token"]; exists {
		t.Fatal("worker_token should not be present in first enrollment")
	}
	if _, exists := req["reconnect"]; exists {
		t.Fatal("reconnect should not be present in first enrollment")
	}
}
