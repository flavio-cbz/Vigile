package policy

import (
	"crypto/ed25519"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"time"

	"github.com/flavio-cbz/Vigile/worker/protocol"
)

// VerifyPolicyBundle validates a raw PolicyBundle payload:
// 1. Checks node_id matches current worker node_id
// 2. Checks timestamp bounds (expires_at > now)
// 3. Verifies anti-rollback rules (epoch / version) unless recovery: true with dual admin proof
// 4. Strips signature, canonicalizes payload via RFC 8785 (JCS), and verifies Ed25519 signature against masterPub
func VerifyPolicyBundle(bundle *PolicyBundle, currentPolicy *PolicyBundle, masterPub ed25519.PublicKey, currentNodeID string) error {
	if bundle == nil {
		return fmt.Errorf("policy bundle is nil")
	}

	if bundle.NodeID != currentNodeID {
		return fmt.Errorf("policy node_id mismatch: got %q, want %q", bundle.NodeID, currentNodeID)
	}

	now := float64(time.Now().Unix())
	if bundle.ExpiresAt > 0 && now > bundle.ExpiresAt {
		return fmt.Errorf("policy bundle expired at %f (now %f)", bundle.ExpiresAt, now)
	}

	// Anti-rollback check
	if currentPolicy != nil {
		if bundle.MasterKeyID == currentPolicy.MasterKeyID && bundle.PolicyEpoch == currentPolicy.PolicyEpoch {
			if bundle.PolicyVersion <= currentPolicy.PolicyVersion && !bundle.IsRecovery {
				return fmt.Errorf("policy version rollback rejected: got %d <= current %d", bundle.PolicyVersion, currentPolicy.PolicyVersion)
			}
		} else if bundle.PolicyEpoch < currentPolicy.PolicyEpoch && !bundle.IsRecovery {
			return fmt.Errorf("policy epoch rollback rejected: got %d < current %d", bundle.PolicyEpoch, currentPolicy.PolicyEpoch)
		}
	}

	// Recovery bundle checks
	if bundle.IsRecovery {
		if len(bundle.ApprovedByAdmins) < 2 {
			return fmt.Errorf("recovery bundle requires at least 2 distinct admin approvals")
		}
		if bundle.RecoveryTicketID == "" {
			return fmt.Errorf("recovery bundle requires valid recovery_ticket_id")
		}
	}

	// Verify Ed25519 Signature
	sigBytes, err := base64.RawURLEncoding.DecodeString(bundle.Signature)
	if err != nil {
		sigBytes, err = base64.StdEncoding.DecodeString(bundle.Signature)
		if err != nil {
			return fmt.Errorf("invalid signature base64 encoding: %w", err)
		}
	}

	// Construct payload without signature field for JCS canonicalization
	payloadMap := map[string]interface{}{
		"policy_id":             bundle.PolicyID,
		"node_id":               bundle.NodeID,
		"master_key_id":         bundle.MasterKeyID,
		"policy_epoch":          bundle.PolicyEpoch,
		"policy_version":        bundle.PolicyVersion,
		"issued_at":             bundle.IssuedAt,
		"expires_at":            bundle.ExpiresAt,
		"rules":                 bundle.Rules,
	}
	if bundle.IsRecovery {
		payloadMap["recovery"] = true
		payloadMap["recovery_ticket_id"] = bundle.RecoveryTicketID
		payloadMap["approved_by_admins"] = bundle.ApprovedByAdmins
	}

	rawJSON, err := json.Marshal(payloadMap)
	if err != nil {
		return fmt.Errorf("failed to marshal policy payload: %w", err)
	}

	canonicalBytes, err := protocol.CanonicalizeJSON(rawJSON)
	if err != nil {
		return fmt.Errorf("RFC 8785 canonicalization failed: %w", err)
	}

	if !ed25519.Verify(masterPub, canonicalBytes, sigBytes) {
		return fmt.Errorf("Ed25519 signature verification failed")
	}

	return nil
}
