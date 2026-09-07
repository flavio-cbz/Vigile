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
	Attempts        int       `json:"attempts,omitempty"`
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
	err := os.Remove(getPendingPath())
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
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

	state.Attempts++
	if updatedData, err := json.Marshal(state); err == nil {
		_ = sys.WriteFileAtomic(pendingPath, updatedData, 0600)
	}

	// If pending update is older than 60s or failed >= 5 times, trigger rollback
	if state.Attempts >= 5 || time.Since(state.UpdatedAt) > 60*time.Second {
		backupPath := execPath + ".previous"
		if _, err := os.Stat(backupPath); err == nil && execPath != "" {
			tmpRestore := execPath + ".restore.tmp"
			if err := sys.CopyFile(backupPath, tmpRestore, 0755); err == nil {
				if rErr := os.Rename(tmpRestore, execPath); rErr != nil {
					slog.Warn("automated rollback: failed to rename restored binary", "error", rErr)
				}
			} else {
				slog.Warn("automated rollback: failed to copy backup binary to tmp", "backup_path", backupPath, "tmp", tmpRestore, "error", err)
			}
		}

		// Symlink restoration if previous release link exists
		if prevTarget, err := os.Readlink(DefaultPreviousLink); err == nil && prevTarget != "" {
			if rErr := os.Remove(DefaultCurrentLink); rErr == nil || os.IsNotExist(rErr) {
				if err := os.Symlink(prevTarget, DefaultCurrentLink); err != nil {
					slog.Warn("automated rollback: failed to restore current symlink", "target", prevTarget, "error", err)
				}
			}
		}

		if err := os.Remove(pendingPath); err != nil {
			slog.Debug("failed to remove pending update file after rollback", "path", pendingPath, "error", err)
		}
		return true, fmt.Errorf("automated rollback performed for failed update version %s after %d attempts", state.NewVersion, state.Attempts)
	}

	return false, nil
}
