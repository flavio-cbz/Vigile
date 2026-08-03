package updater

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

// ReleaseManifest defines a signed binary release offered by Master.
type ReleaseManifest struct {
	ReleaseID     string `json:"release_id"`
	WorkerVersion string `json:"worker_version"`
	OS            string `json:"os"`
	Arch          string `json:"arch"`
	ProtocolMin   int    `json:"protocol_min"`
	ProtocolMax   int    `json:"protocol_max"`
	URL           string `json:"url"`
	SHA256        string `json:"sha256"`
	SizeBytes     int64  `json:"size_bytes"`
	Signature     string `json:"signature"`
}

// VerifyReleaseManifest validates the Ed25519 signature of a ReleaseManifest using JCS RFC 8785.
func VerifyReleaseManifest(manifest *ReleaseManifest, masterPub ed25519.PublicKey) error {
	if manifest == nil {
		return fmt.Errorf("release manifest is nil")
	}

	if manifest.Signature == "" {
		return fmt.Errorf("release manifest signature is missing")
	}

	sigBytes, err := base64.RawURLEncoding.DecodeString(manifest.Signature)
	if err != nil {
		sigBytes, err = base64.StdEncoding.DecodeString(manifest.Signature)
		if err != nil {
			return fmt.Errorf("invalid release manifest signature base64: %w", err)
		}
	}

	manifestMap := map[string]interface{}{
		"release_id":     manifest.ReleaseID,
		"worker_version": manifest.WorkerVersion,
		"os":             manifest.OS,
		"arch":           manifest.Arch,
		"protocol_min":   manifest.ProtocolMin,
		"protocol_max":   manifest.ProtocolMax,
		"url":            manifest.URL,
		"sha256":         manifest.SHA256,
		"size_bytes":     manifest.SizeBytes,
	}

	rawJSON, err := json.Marshal(manifestMap)
	if err != nil {
		return fmt.Errorf("marshal manifest payload failed: %w", err)
	}

	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		return fmt.Errorf("RFC 8785 canonicalization failed: %w", err)
	}

	if !ed25519.Verify(masterPub, canonicalBytes, sigBytes) {
		return fmt.Errorf("Ed25519 signature verification failed for release manifest")
	}

	return nil
}
