package updater

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"github.com/flavio-cbz/Vigile/worker/sys"
)

var PendingFilePath = "/var/lib/vigile/update_pending.json"

func getPendingPath() string {
	if _, err := os.Stat(filepath.Dir(PendingFilePath)); err == nil {
		return PendingFilePath
	}
	return "/tmp/vigile_update_pending.json"
}

type UpdatePendingState struct {
	PreviousVersion string    `json:"previous_version"`
	NewVersion      string    `json:"new_version"`
	UpdatedAt       time.Time `json:"updated_at"`
	Confirmed       bool      `json:"confirmed"`
}

// MarkUpdatePending writes update metadata prior to process restart.
func MarkUpdatePending(prevVer, newVer string) error {
	state := UpdatePendingState{
		PreviousVersion: prevVer,
		NewVersion:      newVer,
		UpdatedAt:       time.Now(),
		Confirmed:       false,
	}
	data, err := json.Marshal(state)
	if err != nil {
		return err
	}
	return sys.WriteFileAtomic(getPendingPath(), data, 0600)
}

// ConfirmUpdate clears update pending state upon successful WSS connection / heartbeat.
func ConfirmUpdate() error {
	return os.Remove(getPendingPath())
}

// CheckAndRollbackIfFailed checks if pending update timed out without confirmation and performs automated rollback.
func CheckAndRollbackIfFailed(execPath string) (bool, error) {
	pendingPath := getPendingPath()
	data, err := os.ReadFile(pendingPath)
	if err != nil {
		return false, nil // No pending update file found
	}

	var state UpdatePendingState
	if err := json.Unmarshal(data, &state); err != nil {
		if err := os.Remove(pendingPath); err != nil {
			slog.Debug("failed to remove pending update file after unmarshal error", "path", pendingPath, "error", err)
		}
		return false, nil
	}

	if state.Confirmed {
		if err := os.Remove(pendingPath); err != nil {
			slog.Debug("failed to remove confirmed pending update file", "path", pendingPath, "error", err)
		}
		return false, nil
	}

	// If pending update is older than 60s, trigger rollback
	if time.Since(state.UpdatedAt) > 60*time.Second {
		backupPath := execPath + ".previous"
		if _, err := os.Stat(backupPath); err == nil && execPath != "" {
			if err := sys.CopyFile(backupPath, execPath, 0755); err != nil {
				slog.Warn("automated rollback: failed to restore backup binary", "backup_path", backupPath, "exec_path", execPath, "error", err)
			}
		}
		if err := os.Remove(pendingPath); err != nil {
			slog.Debug("failed to remove pending update file after rollback", "path", pendingPath, "error", err)
		}
		return true, fmt.Errorf("automated rollback performed for failed update version %s", state.NewVersion)
	}

	return false, nil
}
