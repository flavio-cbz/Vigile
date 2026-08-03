package policy

import "github.com/flavio-cbz/Vigile/worker/protocol"

// PolicyBundle represents an Ed25519-signed policy bundle received from Master.
type PolicyBundle struct {
	PolicyID            string                `json:"policy_id"`
	NodeID              string                `json:"node_id"`
	MasterKeyID         string                `json:"master_key_id"`
	PolicyEpoch         int64                 `json:"policy_epoch"`
	PolicyVersion       int64                 `json:"policy_version"`
	IssuedAt            float64               `json:"issued_at"`
	ExpiresAt           float64               `json:"expires_at"`
	IsRecovery          bool                  `json:"recovery,omitempty"`
	RecoveryTicketID    string                `json:"recovery_ticket_id,omitempty"`
	ApprovedByAdmins    []string              `json:"approved_by_admins,omitempty"`
	Rules               []protocol.PolicyRule `json:"rules"`
	Signature           string                `json:"signature"`
	Admin2RecoveryProof string                `json:"recovery_proof,omitempty"`
}

// ActivePolicyState holds the current verified policy in memory and meta info.
type ActivePolicyState struct {
	Bundle      *PolicyBundle `json:"bundle"`
	BundleHash  string        `json:"bundle_hash"`
	AppliedAt   float64       `json:"applied_at"`
	MasterPub   []byte        `json:"-"`
}
