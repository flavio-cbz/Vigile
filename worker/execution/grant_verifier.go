package execution

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

// VerifyExecutionGrant validates a signed execution_grant for a mutating action:
// 1. Ensures execution_grant signature string is non-empty
// 2. Checks expiration window (expires_at > now)
// 3. Serializes grant parameters deterministically with RFC 8785 (JCS)
// 4. Verifies Ed25519 signature against masterPub
func VerifyExecutionGrant(req *protocol.ActionRequestPayload, masterPub ed25519.PublicKey) error {
	if req.ExecutionGrant == "" {
		return fmt.Errorf("mutating action %q requires a signed execution_grant", req.Action)
	}

	now := float64(time.Now().Unix())
	if req.ExpiresAt > 0 && now > req.ExpiresAt {
		return fmt.Errorf("execution grant expired at %f (now %f)", req.ExpiresAt, now)
	}

	sigBytes, err := base64.RawURLEncoding.DecodeString(req.ExecutionGrant)
	if err != nil {
		sigBytes, err = base64.StdEncoding.DecodeString(req.ExecutionGrant)
		if err != nil {
			return fmt.Errorf("invalid execution grant base64 signature: %w", err)
		}
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

	rawJSON, err := json.Marshal(grantMap)
	if err != nil {
		return fmt.Errorf("marshal grant payload failed: %w", err)
	}

	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		return fmt.Errorf("RFC 8785 canonicalization of grant failed: %w", err)
	}

	if !ed25519.Verify(masterPub, canonicalBytes, sigBytes) {
		return fmt.Errorf("execution_grant Ed25519 signature verification failed")
	}

	return nil
}
