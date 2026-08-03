package updater

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/flavio-cbz/Vigile/worker/sys"
)

const (
	DefaultVigileDir     = "/var/lib/vigile"
	DefaultReleasesDir   = "/var/lib/vigile/releases"
	DefaultCurrentLink   = "/var/lib/vigile/worker.current"
	DefaultPreviousLink  = "/var/lib/vigile/worker.previous"
)

// PromoteStagedRelease promotes a staged binary to active worker.current and preserves worker.previous.
func PromoteStagedRelease(stagedPath, version string, execPath string) error {
	releasesDir := DefaultReleasesDir
	if err := os.MkdirAll(releasesDir, 0755); err != nil {
		releasesDir = filepath.Dir(execPath)
	}

	targetReleasePath := filepath.Join(releasesDir, fmt.Sprintf("worker-%s", version))
	_ = os.Remove(targetReleasePath)

	// Move staged file to release path
	if err := os.Rename(stagedPath, targetReleasePath); err != nil {
		// Cross-device move fallback
		if err := sys.CopyFile(stagedPath, targetReleasePath, 0755); err != nil {
			return fmt.Errorf("failed to promote staged binary to %s: %w", targetReleasePath, err)
		}
		_ = os.Remove(stagedPath)
	}

	_ = os.Chmod(targetReleasePath, 0755)

	// If execPath is directly a file rather than symlink (e.g. /usr/local/bin/vigile-worker),
	// attempt atomic replacement or copy fallback
	if execPath != "" && execPath != DefaultCurrentLink {
		backupPath := execPath + ".previous"
		_ = os.Remove(backupPath)
		_ = os.Rename(execPath, backupPath)

		if err := sys.CopyFile(targetReleasePath, execPath, 0755); err != nil {
			_ = os.Rename(backupPath, execPath) // Rollback
			return fmt.Errorf("failed to copy binary to execPath %s: %w", execPath, err)
		}
	}

	// Update current symlink
	_ = os.Remove(DefaultPreviousLink)
	if curTarget, err := os.Readlink(DefaultCurrentLink); err == nil {
		_ = os.Symlink(curTarget, DefaultPreviousLink)
	}

	tmpLink := DefaultCurrentLink + ".tmp"
	_ = os.Remove(tmpLink)
	if err := os.Symlink(targetReleasePath, tmpLink); err == nil {
		_ = os.Rename(tmpLink, DefaultCurrentLink)
	}

	return nil
}
