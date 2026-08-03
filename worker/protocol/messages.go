package protocol

import "encoding/json"

// Message Types
const (
	MsgTypeHello               = "HELLO"
	MsgTypeHeartbeat           = "HEARTBEAT"
	MsgTypeInventorySnapshot   = "INVENTORY_SNAPSHOT"
	MsgTypeMetricsSnapshot     = "METRICS_SNAPSHOT"
	MsgTypePolicyBundle        = "POLICY_BUNDLE"
	MsgTypePolicyApplied       = "POLICY_APPLIED"
	MsgTypePolicyRejected      = "POLICY_REJECTED"
	MsgTypeActionRequest       = "ACTION_REQUEST"
	MsgTypeActionResult        = "ACTION_RESULT"
	MsgTypeWorkerUpdateOffer   = "WORKER_UPDATE_OFFER"
	MsgTypeWorkerUpdateResult  = "WORKER_UPDATE_RESULT"
)

// BaseMessage wraps all WSS messages on the wire.
type BaseMessage struct {
	Type    string          `json:"type"`
	Payload json.RawMessage `json:"payload"`
}

// CanonicalTarget defines a target resource canonically across Python and Go.
type CanonicalTarget struct {
	Kind string `json:"kind"` // e.g. "systemd_service", "docker_container", "directory", "mount"
	ID   string `json:"id"`   // e.g. "nginx.service", "98e8d0d12aab", "/var/log"
}

// PolicyRule describes a single permission rule inside a POLICY_BUNDLE.
type PolicyRule struct {
	RuleID                string                 `json:"rule_id"`
	PluginID              string                 `json:"plugin_id"`
	Action                string                 `json:"action"`
	Target                CanonicalTarget        `json:"target"`
	Limits                map[string]interface{} `json:"limits,omitempty"`
	RequiresHumanApproval bool                   `json:"requires_human_approval"`
}

// PolicyBundlePayload is sent by Master to Worker to configure local authorizations.
type PolicyBundlePayload struct {
	PolicyID            string       `json:"policy_id"`
	NodeID              string       `json:"node_id"`
	MasterKeyID         string       `json:"master_key_id"`
	PolicyEpoch         int64        `json:"policy_epoch"`
	PolicyVersion       int64        `json:"policy_version"`
	IssuedAt            float64      `json:"issued_at"`
	ExpiresAt           float64      `json:"expires_at"`
	IsRecovery          bool         `json:"recovery,omitempty"`
	RecoveryTicketID    string       `json:"recovery_ticket_id,omitempty"`
	ApprovedByAdmins    []string     `json:"approved_by_admins,omitempty"`
	Rules               []PolicyRule `json:"rules"`
	Signature           string       `json:"signature"`             // Ed25519 signature of RFC8785 canonical bytes (without signature field)
	Admin2RecoveryProof string       `json:"recovery_proof,omitempty"`
}

// ActionRequestPayload is sent by Master to execute an authorized action on a Worker.
type ActionRequestPayload struct {
	RequestID      string          `json:"request_id"`
	ProposalID     string          `json:"proposal_id"`
	PolicyID       string          `json:"policy_id"`
	PolicyVersion  int64           `json:"policy_version"`
	Action         string          `json:"action"`
	Target         CanonicalTarget `json:"target"`
	Params         map[string]any  `json:"params,omitempty"`
	ApprovedBy     string          `json:"approved_by"`
	ApprovedAt     float64         `json:"approved_at"`
	ExpiresAt      float64         `json:"expires_at"`
	ExecutionGrant string          `json:"execution_grant"` // Ed25519 signature of grant payload
}

// ActionResultPayload is sent by Worker to Master reporting execution status.
type ActionResultPayload struct {
	RequestID  string `json:"request_id"`
	ProposalID string `json:"proposal_id"`
	Success    bool   `json:"success"`
	Output     string `json:"output,omitempty"`
	Error      string `json:"error,omitempty"`
	Code       int    `json:"code,omitempty"`
	DurationMS int64  `json:"duration_ms"`
}

// PolicyAppliedPayload is sent by Worker to acknowledge policy activation.
type PolicyAppliedPayload struct {
	PolicyID      string   `json:"policy_id"`
	PolicyVersion int64    `json:"policy_version"`
	BundleHash    string   `json:"bundle_hash"`
	AppliedAt     float64  `json:"applied_at"`
	ValidatedRules int     `json:"validated_rules"`
	RejectedRules []string `json:"rejected_rules,omitempty"`
}

// PolicyRejectedPayload is sent by Worker if policy validation fails.
type PolicyRejectedPayload struct {
	PolicyID      string  `json:"policy_id"`
	PolicyVersion int64   `json:"policy_version"`
	Reason        string  `json:"reason"`
	RejectedAt    float64 `json:"rejected_at"`
}
