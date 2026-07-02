package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

// b64enc is URL-safe base64 with padding (matching Python's urlsafe_b64encode).
var b64enc = base64.URLEncoding

// KeyPaths for the Ed25519 keypair.
var (
	keyDir          = defaultKeyDir()
	privateKeyPath  = filepath.Join(keyDir, "worker.key")
	publicKeyPath   = filepath.Join(keyDir, "worker.key.pub")
	tokenPath       = filepath.Join(keyDir, "enrollment.token")
	masterURLPath   = filepath.Join(keyDir, "master_url")
	workerTokenPath = filepath.Join(keyDir, "worker_token")
)

func defaultKeyDir() string {
	if runtime.GOOS == "windows" {
		programData := os.Getenv("ProgramData")
		if programData == "" {
			programData = `C:\ProgramData`
		}
		return filepath.Join(programData, "vigile")
	}
	return "/etc/vigile"
}

func setKeyDir(dir string) {
	keyDir = dir
	privateKeyPath = filepath.Join(keyDir, "worker.key")
	publicKeyPath = filepath.Join(keyDir, "worker.key.pub")
	tokenPath = filepath.Join(keyDir, "enrollment.token")
	masterURLPath = filepath.Join(keyDir, "master_url")
	workerTokenPath = filepath.Join(keyDir, "worker_token")
}

// loadOrGenerateKeypair loads the Ed25519 keypair from disk, or generates a new one.
func loadOrGenerateKeypair() (ed25519.PrivateKey, ed25519.PublicKey, error) {
	if _, err := os.Stat(privateKeyPath); err == nil {
		privData, err := os.ReadFile(privateKeyPath)
		if err != nil {
			return nil, nil, fmt.Errorf("reading private key: %w", err)
		}
		priv := ed25519.PrivateKey(privData)
		pub := priv.Public().(ed25519.PublicKey)
		return priv, pub, nil
	}

	// Generate new keypair
	pub, priv, err := ed25519.GenerateKey(rand.Reader)
	if err != nil {
		return nil, nil, fmt.Errorf("generating keypair: %w", err)
	}

	// Persist keys
	if err := os.MkdirAll(keyDir, 0700); err != nil {
		return nil, nil, fmt.Errorf("creating key dir: %w", err)
	}
	if err := os.WriteFile(privateKeyPath, priv, 0400); err != nil {
		return nil, nil, fmt.Errorf("writing private key: %w", err)
	}
	pubData, _ := json.Marshal(pub)
	if err := os.WriteFile(publicKeyPath, pubData, 0444); err != nil {
		return nil, nil, fmt.Errorf("writing public key: %w", err)
	}

	logger.Printf("Ed25519 keypair generated and saved to %s", keyDir)
	return priv, pub, nil
}

// buildEnrollmentRequest builds the ENROLLMENT_REQUEST message.
// When workerToken is provided (reconnect mode), it is sent instead of join_token
// and reconnect:true is set to signal the master to skip the Ed25519 challenge.
func buildEnrollmentRequest(joinToken, workerToken string, pub ed25519.PublicKey, fp Fingerprint) map[string]interface{} {
	req := map[string]interface{}{
		"type":       "ENROLLMENT_REQUEST",
		"join_token": joinToken,
		"public_key": b64enc.EncodeToString(pub),
		"fingerprint": map[string]string{
			"hostname":   fp.Hostname,
			"machine_id": fp.MachineID,
			"arch":       fp.Arch,
			"os":         fp.OS,
		},
	}
	if workerToken != "" {
		req["join_token"] = ""
		req["worker_token"] = workerToken
		req["reconnect"] = true
	}
	return req
}

// signChallenge signs a challenge string with the Ed25519 private key.
func signChallenge(priv ed25519.PrivateKey, challenge string) string {
	sig := ed25519.Sign(priv, []byte(challenge))
	return b64enc.EncodeToString(sig)
}

// buildEnrollmentResponse builds the ENROLLMENT_RESPONSE message.
func buildEnrollmentResponse(priv ed25519.PrivateKey, challenge string) map[string]interface{} {
	return map[string]interface{}{
		"type":      "ENROLLMENT_RESPONSE",
		"signature": signChallenge(priv, challenge),
	}
}

// readJoinToken reads the JOIN_TOKEN from file or uses the flag override.
func readJoinToken(tokenOverride string) (string, error) {
	if tokenOverride != "" {
		return tokenOverride, nil
	}
	data, err := os.ReadFile(tokenPath)
	if err != nil {
		return "", fmt.Errorf("reading token file: %w", err)
	}
	return strings.TrimSpace(string(data)), nil
}

// persistWorkerToken writes the worker_token to disk with secure permissions (mode 0600).
func persistWorkerToken(token string) error {
	if token == "" {
		return fmt.Errorf("cannot persist empty worker token")
	}
	if err := os.MkdirAll(keyDir, 0700); err != nil {
		return fmt.Errorf("creating key dir for worker token: %w", err)
	}
	if err := os.WriteFile(workerTokenPath, []byte(token), 0600); err != nil {
		return fmt.Errorf("persisting worker token: %w", err)
	}
	logger.Printf("Worker token persisted to %s", workerTokenPath)
	return nil
}

// readWorkerToken reads the worker_token from disk.
// Returns empty string if file does not exist (non-fatal).
func readWorkerToken() (string, error) {
	data, err := os.ReadFile(workerTokenPath)
	if err != nil {
		if os.IsNotExist(err) {
			return "", nil
		}
		return "", fmt.Errorf("reading worker token: %w", err)
	}
	return strings.TrimSpace(string(data)), nil
}

// computeTokenHash returns SHA256 hex of the token (matching master's join_token_hash).
func computeTokenHash(token string) string {
	h := sha256.Sum256([]byte(token))
	return fmt.Sprintf("%x", h)
}

// getMasterURL reads the master URL from file or uses the flag override.
func getMasterURL(urlOverride string) string {
	if urlOverride != "" {
		return urlOverride
	}
	data, err := os.ReadFile(masterURLPath)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}
