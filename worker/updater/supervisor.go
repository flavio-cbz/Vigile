package updater

import (
	"fmt"
	"log/slog"
	"os"
	"path/filepath"

	"github.com/flavio-cbz/Vigile/worker/sys"
)

const (
	DefaultVigileDir    = "/var/lib/vigile"
	DefaultReleasesDir  = "/var/lib/vigile/releases"
	DefaultCurrentLink  = "/var/lib/vigile/worker.current"
	DefaultPreviousLink = "/var/lib/vigile/worker.previous"
)

// PromoteStagedRelease promotes a staged binary to active worker.current and preserves worker.previous.
func PromoteStagedRelease(stagedPath, version string, execPath string) error {
	releasesDir := DefaultReleasesDir
	if err := os.MkdirAll(releasesDir, 0755); err != nil {
		releasesDir = filepath.Dir(execPath)
	}

	targetReleasePath := filepath.Join(releasesDir, fmt.Sprintf("worker-%s", version))
	if err := os.Remove(targetReleasePath); err != nil && !os.IsNotExist(err) {
		slog.Debug("failed to remove stale target release path", "path", targetReleasePath, "error", err)
	}

	// Move staged file to release path
	if err := os.Rename(stagedPath, targetReleasePath); err != nil {
		// Cross-device move fallback
		if err := sys.CopyFile(stagedPath, targetReleasePath, 0755); err != nil {
			return fmt.Errorf("failed to promote staged binary to %s: %w", targetReleasePath, err)
		}
		if err := os.Remove(stagedPath); err != nil {
			slog.Debug("failed to remove staged file after cross-device copy", "path", stagedPath, "error", err)
		}
	}

	if err := os.Chmod(targetReleasePath, 0755); err != nil {
		slog.Warn("failed to chmod target release path", "path", targetReleasePath, "error", err)
	}

	// If execPath is directly a file rather than symlink (e.g. /usr/local/bin/vigile-worker),
	// attempt atomic replacement or copy fallback
	if execPath != "" && execPath != DefaultCurrentLink {
		backupPath := execPath + ".previous"
		if err := os.Remove(backupPath); err != nil && !os.IsNotExist(err) {
			slog.Debug("failed to remove stale backup path", "path", backupPath, "error", err)
		}
		if err := os.Rename(execPath, backupPath); err != nil {
			slog.Warn("failed to create backup of current binary", "exec_path", execPath, "backup_path", backupPath, "error", err)
		}

		if err := sys.CopyFile(targetReleasePath, execPath, 0755); err != nil {
			if err := os.Rename(backupPath, execPath); err != nil {
				slog.Error("rollback failed: could not restore backup binary after copy failure", "backup_path", backupPath, "exec_path", execPath, "error", err)
			}
			return fmt.Errorf("failed to copy binary to execPath %s: %w", execPath, err)
		}
	}

	// Update current symlink
	if err := os.Remove(DefaultPreviousLink); err != nil && !os.IsNotExist(err) {
		slog.Debug("failed to remove previous link", "path", DefaultPreviousLink, "error", err)
	}
	if curTarget, err := os.Readlink(DefaultCurrentLink); err == nil {
		if err := os.Symlink(curTarget, DefaultPreviousLink); err != nil {
			slog.Warn("failed to create previous symlink", "target", curTarget, "link", DefaultPreviousLink, "error", err)
		}
	}

	tmpLink := DefaultCurrentLink + ".tmp"
	if err := os.Remove(tmpLink); err != nil && !os.IsNotExist(err) {
		slog.Debug("failed to remove stale tmp link", "path", tmpLink, "error", err)
	}
	if err := os.Symlink(targetReleasePath, tmpLink); err == nil {
		if err := os.Rename(tmpLink, DefaultCurrentLink); err != nil {
			slog.Warn("failed to promote tmp link to current", "tmp_link", tmpLink, "current_link", DefaultCurrentLink, "error", err)
		}
	}

	return nil
}
