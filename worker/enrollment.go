package main

import (
	"crypto/ed25519"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// b64enc is URL-safe base64 with padding (matching Python's urlsafe_b64encode).
var b64enc = base64.URLEncoding

// KeyPaths for the Ed25519 keypair.
const (
	keyDir         = "/etc/youcloud"
	privateKeyPath = keyDir + "/worker.key"
	publicKeyPath  = keyDir + "/worker.key.pub"
	tokenPath      = keyDir + "/enrollment.token"
	masterURLPath  = keyDir + "/master_url"
)

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
func buildEnrollmentRequest(joinToken string, pub ed25519.PublicKey, fp Fingerprint) map[string]interface{} {
	return map[string]interface{}{
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
