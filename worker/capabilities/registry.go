package capabilities

// RiskTier represents the security authorization level required for a primitive.
type RiskTier string

const (
	Tier1PassivePush   RiskTier = "TIER1_PASSIVE_PUSH"    // No policy required (Metrics, Inventory, Global Mount stats)
	Tier2TargetedRead  RiskTier = "TIER2_TARGETED_READ"   // Signed Policy required (Status, Log source, Directory usage)
	Tier3GlobalRead    RiskTier = "TIER3_GLOBAL_READ"     // Explicit Admin Policy grant required (List Services, List Containers)
	Tier4Mutating      RiskTier = "TIER4_MUTATING"        // Policy + Signed Execution Grant (RELOAD_SERVICE, RESTART_SERVICE, RESTART_CONTAINER)
)

// PrimitiveMeta defines metadata for a compiled Worker primitive.
type PrimitiveMeta struct {
	Name            string   `json:"name"`
	Risk            RiskTier `json:"risk_tier"`
	TargetKind      string   `json:"target_kind"` // e.g. "systemd_service", "docker_container", "directory", "mount", ""
	RequiresGrant   bool     `json:"requires_grant"`
	RequiresPolicy  bool     `json:"requires_policy"`
	IsMutating      bool     `json:"is_mutating"`
}

// Registry maps primitive names to their immutable metadata definitions.
var Registry = map[string]PrimitiveMeta{
	// Tier 1: Passive Push Telemetry
	"METRICS_SNAPSHOT": {
		Name:           "METRICS_SNAPSHOT",
		Risk:           Tier1PassivePush,
		RequiresPolicy: false,
	},
	"INVENTORY_SNAPSHOT": {
		Name:           "INVENTORY_SNAPSHOT",
		Risk:           Tier1PassivePush,
		RequiresPolicy: false,
	},
	"GET_FILESYSTEM_USAGE": {
		Name:           "GET_FILESYSTEM_USAGE",
		Risk:           Tier1PassivePush,
		TargetKind:     "mount",
		RequiresPolicy: false,
	},

	// Tier 2: Targeted Read
	"GET_SERVICE_STATUS": {
		Name:           "GET_SERVICE_STATUS",
		Risk:           Tier2TargetedRead,
		TargetKind:     "systemd_service",
		RequiresPolicy: true,
	},
	"GET_CONTAINER_STATUS": {
		Name:           "GET_CONTAINER_STATUS",
		Risk:           Tier2TargetedRead,
		TargetKind:     "docker_container",
		RequiresPolicy: true,
	},
	"READ_LOG_SOURCE": {
		Name:           "READ_LOG_SOURCE",
		Risk:           Tier2TargetedRead,
		TargetKind:     "log_source",
		RequiresPolicy: true,
	},
	"GET_DIRECTORY_USAGE": {
		Name:           "GET_DIRECTORY_USAGE",
		Risk:           Tier2TargetedRead,
		TargetKind:     "directory",
		RequiresPolicy: true,
	},
	"FIND_LARGE_FILES": {
		Name:           "FIND_LARGE_FILES",
		Risk:           Tier2TargetedRead,
		TargetKind:     "directory",
		RequiresPolicy: true,
	},
	"GET_DOCKER_DISK_USAGE": {
		Name:           "GET_DOCKER_DISK_USAGE",
		Risk:           Tier2TargetedRead,
		TargetKind:     "docker_host",
		RequiresPolicy: true,
	},
	"GET_LOG_RETENTION_SUMMARY": {
		Name:           "GET_LOG_RETENTION_SUMMARY",
		Risk:           Tier2TargetedRead,
		TargetKind:     "log_scope",
		RequiresPolicy: true,
	},

	// Tier 3: Global Discovery Read
	"LIST_SERVICES": {
		Name:           "LIST_SERVICES",
		Risk:           Tier3GlobalRead,
		RequiresPolicy: true,
	},
	"LIST_CONTAINERS": {
		Name:           "LIST_CONTAINERS",
		Risk:           Tier3GlobalRead,
		RequiresPolicy: true,
	},
	"LIST_LOG_SOURCES": {
		Name:           "LIST_LOG_SOURCES",
		Risk:           Tier3GlobalRead,
		RequiresPolicy: true,
	},

	// Tier 4: Mutating Primitives
	"RELOAD_SERVICE": {
		Name:           "RELOAD_SERVICE",
		Risk:           Tier4Mutating,
		TargetKind:     "systemd_service",
		RequiresPolicy: true,
		RequiresGrant:  true,
		IsMutating:     true,
	},
	"RESTART_SERVICE": {
		Name:           "RESTART_SERVICE",
		Risk:           Tier4Mutating,
		TargetKind:     "systemd_service",
		RequiresPolicy: true,
		RequiresGrant:  true,
		IsMutating:     true,
	},
	"RESTART_CONTAINER": {
		Name:           "RESTART_CONTAINER",
		Risk:           Tier4Mutating,
		TargetKind:     "docker_container",
		RequiresPolicy: true,
		RequiresGrant:  true,
		IsMutating:     true,
	},
}

// IsPrimitiveSupported checks if primitive exists in registry.
func IsPrimitiveSupported(action string) bool {
	_, exists := Registry[action]
	return exists
}
