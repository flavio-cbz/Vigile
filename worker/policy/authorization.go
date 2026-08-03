package policy

import (
	"fmt"
	"strings"
	"time"

	"github.com/flavio-cbz/Vigile/worker/capabilities"
	"github.com/flavio-cbz/Vigile/worker/protocol"
)

// AuthorizationResult contains decision feedback from the policy engine.
type AuthorizationResult struct {
	Authorized      bool                      `json:"authorized"`
	Reason          string                    `json:"reason"`
	MatchedRule     *protocol.PolicyRule      `json:"matched_rule,omitempty"`
	EffectiveBudget capabilities.BudgetLimits `json:"effective_budget"`
}

// AuthorizeAction evaluates whether an incoming primitive action targeting a specific resource is permitted.
func AuthorizeAction(activeState *ActivePolicyState, action string, target protocol.CanonicalTarget, params map[string]interface{}) AuthorizationResult {
	meta, exists := capabilities.Registry[action]
	if !exists {
		return AuthorizationResult{
			Authorized: false,
			Reason:     fmt.Sprintf("primitive action %q unsupported by worker registry", action),
		}
	}

	// Tier 1: Passive push telemetry doesn't require policy
	if meta.Risk == capabilities.Tier1PassivePush {
		return AuthorizationResult{
			Authorized:      true,
			Reason:          "tier 1 passive telemetry permitted without policy restriction",
			EffectiveBudget: capabilities.EffectiveBudget(action, params),
		}
	}

	if activeState == nil || activeState.Bundle == nil {
		return AuthorizationResult{
			Authorized: false,
			Reason:     "no active signed policy bundle loaded on worker",
		}
	}

	bundle := activeState.Bundle

	// Expiration check: if policy is expired, reject all non-passive requests
	now := float64(time.Now().Unix())
	if bundle.ExpiresAt > 0 && now > bundle.ExpiresAt {
		return AuthorizationResult{
			Authorized: false,
			Reason:     fmt.Sprintf("active policy bundle %s expired at %f", bundle.PolicyID, bundle.ExpiresAt),
		}
	}

	// Rule matching
	for i := range bundle.Rules {
		rule := &bundle.Rules[i]
		if rule.Action != action {
			continue
		}

		// Match target kind & ID
		if meta.TargetKind != "" && rule.Target.Kind != meta.TargetKind {
			continue
		}

		if matchTarget(meta.TargetKind, rule.Target.ID, target.ID) {
			mergedLimits := mergeLimits(rule.Limits, params)
			return AuthorizationResult{
				Authorized:      true,
				Reason:          fmt.Sprintf("authorized by policy rule %s", rule.RuleID),
				MatchedRule:     rule,
				EffectiveBudget: capabilities.EffectiveBudget(action, mergedLimits),
			}
		}
	}

	return AuthorizationResult{
		Authorized: false,
		Reason:     fmt.Sprintf("no active policy rule authorizes primitive %q on target %s:%s", action, target.Kind, target.ID),
	}
}

func matchTarget(kind, ruleTargetID, requestTargetID string) bool {
	if ruleTargetID == "*" || ruleTargetID == requestTargetID {
		return true
	}
	if kind == "directory" || kind == "mount" {
		// Directory/mount prefix match
		cleanRulePath := strings.TrimRight(ruleTargetID, "/")
		cleanReqPath := strings.TrimRight(requestTargetID, "/")
		return cleanReqPath == cleanRulePath || strings.HasPrefix(cleanReqPath, cleanRulePath+"/")
	}
	return false
}

func mergeLimits(ruleLimits map[string]interface{}, params map[string]interface{}) map[string]interface{} {
	merged := make(map[string]interface{})
	for k, v := range ruleLimits {
		merged[k] = v
	}
	for k, v := range params {
		if _, exists := merged[k]; !exists {
			merged[k] = v
		}
	}
	return merged
}
