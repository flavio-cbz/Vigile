package capabilities

import "time"

// BudgetLimits defines compiled safety caps enforced locally by the Worker binary.
// Remote policy budgets can REDUCE these limits, but can NEVER increase them.
type BudgetLimits struct {
	MaxDepth       int           `json:"max_depth"`
	MaxEntries     int           `json:"max_entries"`
	MaxLines       int           `json:"max_lines"`
	MaxBytes       int64         `json:"max_bytes"`
	MaxTimeout     time.Duration `json:"max_timeout"`
	AllowedSubtree string        `json:"allowed_subtree,omitempty"`
}

// DefaultPrimitiveBudgets holds immutable safety caps for each primitive.
var DefaultPrimitiveBudgets = map[string]BudgetLimits{
	"GET_FILESYSTEM_USAGE": {
		MaxTimeout: 5 * time.Second,
	},
	"GET_DIRECTORY_USAGE": {
		MaxDepth:   6,
		MaxEntries: 50000,
		MaxBytes:   262144, // 256 KiB result payload cap
		MaxTimeout: 20 * time.Second,
	},
	"FIND_LARGE_FILES": {
		MaxDepth:   8,
		MaxEntries: 100,
		MaxBytes:   262144,
		MaxTimeout: 15 * time.Second,
	},
	"GET_DOCKER_DISK_USAGE": {
		MaxTimeout: 10 * time.Second,
		MaxBytes:   524288,
	},
	"GET_LOG_RETENTION_SUMMARY": {
		MaxTimeout: 10 * time.Second,
		MaxBytes:   262144,
	},
	"READ_LOG_SOURCE": {
		MaxLines:   1000,
		MaxBytes:   1048576, // 1 MiB
		MaxTimeout: 15 * time.Second,
	},
	"GET_SERVICE_STATUS": {
		MaxTimeout: 5 * time.Second,
	},
	"GET_CONTAINER_STATUS": {
		MaxTimeout: 5 * time.Second,
	},
	"RELOAD_SERVICE": {
		MaxTimeout: 30 * time.Second,
	},
	"RESTART_SERVICE": {
		MaxTimeout: 30 * time.Second,
	},
	"RESTART_CONTAINER": {
		MaxTimeout: 45 * time.Second,
	},
	"LIST_SERVICES": {
		MaxTimeout: 10 * time.Second,
	},
	"LIST_CONTAINERS": {
		MaxTimeout: 10 * time.Second,
	},
	"LIST_LOG_SOURCES": {
		MaxTimeout: 10 * time.Second,
	},
}

// EffectiveBudget calculates the restrictive minimum between compiled limits and requested policy limits.
func EffectiveBudget(primitive string, requestedLimits map[string]interface{}) BudgetLimits {
	compiled, exists := DefaultPrimitiveBudgets[primitive]
	if !exists {
		return BudgetLimits{MaxTimeout: 5 * time.Second}
	}

	result := compiled

	if requestedLimits == nil {
		return result
	}

	if depth, ok := getInt(requestedLimits["max_depth"]); ok && depth > 0 && depth < result.MaxDepth {
		result.MaxDepth = depth
	}

	if entries, ok := getInt(requestedLimits["max_entries"]); ok && entries > 0 && entries < result.MaxEntries {
		result.MaxEntries = entries
	}

	if lines, ok := getInt(requestedLimits["max_lines"]); ok && lines > 0 && lines < result.MaxLines {
		result.MaxLines = lines
	}

	if bytesVal, ok := getInt64(requestedLimits["max_bytes"]); ok && bytesVal > 0 && bytesVal < result.MaxBytes {
		result.MaxBytes = bytesVal
	}

	if timeoutSec, ok := getInt(requestedLimits["timeout_seconds"]); ok && timeoutSec > 0 {
		requestedTimeout := time.Duration(timeoutSec) * time.Second
		if requestedTimeout < result.MaxTimeout {
			result.MaxTimeout = requestedTimeout
		}
	}

	return result
}

func getInt(val interface{}) (int, bool) {
	switch v := val.(type) {
	case int:
		return v, true
	case int64:
		return int(v), true
	case float64:
		return int(v), true
	default:
		return 0, false
	}
}

func getInt64(val interface{}) (int64, bool) {
	switch v := val.(type) {
	case int64:
		return v, true
	case int:
		return int64(v), true
	case float64:
		return int64(v), true
	default:
		return 0, false
	}
}
