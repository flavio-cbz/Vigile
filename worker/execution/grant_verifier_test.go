package execution

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"testing"
	"time"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

func TestVerifyExecutionGrant(t *testing.T) {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		t.Fatalf("failed to generate key: %v", err)
	}

	now := float64(time.Now().Unix())
	req := protocol.ActionRequestPayload{
		RequestID:     "req-001",
		ProposalID:    "prop-001",
		PolicyID:      "pol-001",
		PolicyVersion: 1,
		Action:        "RELOAD_SERVICE",
		Target: protocol.CanonicalTarget{
			Kind: "systemd_service",
			ID:   "nginx.service",
		},
		ApprovedBy: "admin",
		ApprovedAt: now,
		ExpiresAt:  now + 300,
	}

	grantMap := map[string]interface{}{
		"request_id":     req.RequestID,
		"proposal_id":    req.ProposalID,
		"policy_id":      req.PolicyID,
		"policy_version": req.PolicyVersion,
		"action":         req.Action,
		"target": map[string]interface{}{
			"kind": req.Target.Kind,
			"id":   req.Target.ID,
		},
		"approved_by": req.ApprovedBy,
		"approved_at": req.ApprovedAt,
		"expires_at":  req.ExpiresAt,
	}

	rawJSON, _ := json.Marshal(grantMap)
	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		t.Fatalf("canonicalize failed: %v", err)
	}

	sig := ed25519.Sign(priv, canonicalBytes)
	req.ExecutionGrant = base64.RawURLEncoding.EncodeToString(sig)

	t.Run("Valid execution grant passes verification", func(t *testing.T) {
		err := VerifyExecutionGrant(&req, pub)
		if err != nil {
			t.Errorf("unexpected error: %v", err)
		}
	})

	t.Run("Missing grant rejected", func(t *testing.T) {
		badReq := req
		badReq.ExecutionGrant = ""
		err := VerifyExecutionGrant(&badReq, pub)
		if err == nil {
			t.Errorf("expected error for missing grant, got nil")
		}
	})

	t.Run("Expired grant rejected", func(t *testing.T) {
		badReq := req
		badReq.ExpiresAt = now - 10
		err := VerifyExecutionGrant(&badReq, pub)
		if err == nil {
			t.Errorf("expected error for expired grant, got nil")
		}
	})
}
