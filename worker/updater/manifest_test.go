package updater

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"testing"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

func TestVerifyReleaseManifest(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	manifest := ReleaseManifest{
		ReleaseID:     "release-v2.3.0-linux-amd64",
		WorkerVersion: "2.3.0",
		OS:            "linux",
		Arch:          "amd64",
		ProtocolMin:   1,
		ProtocolMax:   2,
		URL:           "/api/worker/binary/linux/amd64",
		SHA256:        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		SizeBytes:     1234567,
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

	rawJSON, _ := json.Marshal(manifestMap)
	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		t.Fatalf("canonicalize failed: %v", err)
	}

	sig := ed25519.Sign(priv, canonicalBytes)
	manifest.Signature = base64.RawURLEncoding.EncodeToString(sig)

	t.Run("Valid release manifest passes verification", func(t *testing.T) {
		err := VerifyReleaseManifest(&manifest, pub)
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("Tampered release manifest rejected", func(t *testing.T) {
		tampered := manifest
		tampered.WorkerVersion = "9.9.9"
		err := VerifyReleaseManifest(&tampered, pub)
		if err == nil {
			t.Errorf("expected error for tampered manifest, got nil")
		}
	})

	t.Run("Missing signature rejected", func(t *testing.T) {
		missingSig := manifest
		missingSig.Signature = ""
		err := VerifyReleaseManifest(&missingSig, pub)
		if err == nil {
			t.Errorf("expected error for missing signature, got nil")
		}
	})
}
