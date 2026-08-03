package policy

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"testing"
	"time"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

func TestVerifyPolicyBundle(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	nodeID := "node-test-123"
	now := float64(time.Now().Unix())

	bundle := PolicyBundle{
		PolicyID:      "pol-001",
		NodeID:        nodeID,
		MasterKeyID:   "key-001",
		PolicyEpoch:   1,
		PolicyVersion: 1,
		IssuedAt:      now,
		ExpiresAt:     now + 3600,
		Rules: []protocol.PolicyRule{
			{
				RuleID:   "rule-1",
				PluginID: "systemd",
				Action:   "RELOAD_SERVICE",
				Target: protocol.CanonicalTarget{
					Kind: "systemd_service",
					ID:   "nginx.service",
				},
				RequiresHumanApproval: true,
			},
		},
	}

	payloadMap := map[string]interface{}{
		"policy_id":      bundle.PolicyID,
		"node_id":        bundle.NodeID,
		"master_key_id":  bundle.MasterKeyID,
		"policy_epoch":   bundle.PolicyEpoch,
		"policy_version": bundle.PolicyVersion,
		"issued_at":      bundle.IssuedAt,
		"expires_at":     bundle.ExpiresAt,
		"rules":          bundle.Rules,
	}

	rawJSON, _ := json.Marshal(payloadMap)
	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		t.Fatalf("canonicalize failed: %v", err)
	}

	sig := ed25519.Sign(priv, canonicalBytes)
	bundle.Signature = base64.RawURLEncoding.EncodeToString(sig)

	t.Run("Valid policy bundle passes verification", func(t *testing.T) {
		err := VerifyPolicyBundle(&bundle, nil, pub, nodeID)
		if err != nil {
			t.Errorf("unexpected verification error: %v", err)
		}
	})

	t.Run("Node ID mismatch rejected", func(t *testing.T) {
		err := VerifyPolicyBundle(&bundle, nil, pub, "other-node")
		if err == nil {
			t.Errorf("expected error for node_id mismatch, got nil")
		}
	})

	t.Run("Anti-rollback version check rejects lower version", func(t *testing.T) {
		oldBundle := bundle
		oldBundle.PolicyVersion = 2

		newBundle := bundle
		newBundle.PolicyVersion = 1

		err := VerifyPolicyBundle(&newBundle, &oldBundle, pub, nodeID)
		if err == nil {
			t.Errorf("expected anti-rollback error, got nil")
		}
	})
}
