package main

import (
	"encoding/json"
	"fmt"
	"log"
)

// nodeID is set during enrollment and used for enrichment in action logs.
var nodeID string

// ALLOWED_ACTIONS is the hardcoded whitelist of actions this Worker can execute.
// Every incoming INTENT is checked against this map before execution.
var ALLOWED_ACTIONS = map[string]bool{
	"GET_STATS":         true,
	"READ_LOGS":         true,
	"RESTART_CONTAINER": true,
	"LIST_CONTAINERS":   true,
	"LIST_SERVICES":     true,
	"STATUS_SERVICE":    true,
	"RESTART_SERVICE":   true,
	"READ_LOGS_SERVICE": true,
}

// Intent describes a command sent by the Master.
type Intent struct {
	IntentID    string                 `json:"intent_id"`
	Action      string                 `json:"action"`
	Params      map[string]interface{} `json:"params,omitempty"`
	RequestedBy string                 `json:"requested_by,omitempty"`
}

// IntentResult is sent back to the Master after execution.
type IntentResult struct {
	IntentID string `json:"intent_id"`
	Success  bool   `json:"success"`
	Output   string `json:"output,omitempty"`
	Error    string `json:"error,omitempty"`
}

// dispatchIntent validates and executes an incoming intent.
func dispatchIntent(raw []byte) []byte {
	var msg Intent
	if err := json.Unmarshal(raw, &msg); err != nil {
		return mustJSON(IntentResult{Error: fmt.Sprintf("invalid JSON: %v", err)})
	}

	// Whitelist check
	if !ALLOWED_ACTIONS[msg.Action] {
		log.Printf("SECURITY: action %q is not in whitelist", msg.Action)
		return mustJSON(IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not allowed", msg.Action),
		})
	}

	log.Printf("Dispatching intent: action=%s id=%s requested_by=%s", msg.Action, msg.IntentID, msg.RequestedBy)

	var result IntentResult
	switch msg.Action {
	case "GET_STATS":
		result = handleGetStats(msg)
	case "READ_LOGS":
		result = handleReadLogs(msg)
	case "LIST_CONTAINERS":
		result = handleListContainers(msg)
	case "RESTART_CONTAINER":
		result = handleRestartContainer(msg)
	case "LIST_SERVICES":
		result = handleListServices(msg)
	case "STATUS_SERVICE":
		result = handleStatusService(msg)
	case "RESTART_SERVICE":
		result = handleRestartService(msg)
	case "READ_LOGS_SERVICE":
		result = handleReadLogsService(msg)
	default:
		result = IntentResult{
			IntentID: msg.IntentID,
			Success:  false,
			Error:    fmt.Sprintf("action %q not implemented", msg.Action),
		}
	}

	result.IntentID = msg.IntentID
	log.Printf("Intent result: id=%s success=%v", result.IntentID, result.Success)
	return mustJSON(result)
}

func mustJSON(v interface{}) []byte {
	data, err := json.Marshal(v)
	if err != nil {
		log.Panicf("json marshal failed: %v", err)
	}
	return data
}
