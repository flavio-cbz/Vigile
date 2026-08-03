package updater

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRollback(t *testing.T) {
	tmpDir, err := os.MkdirTemp("", "vigile-rollback-test-*")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tmpDir)

	execPath := filepath.Join(tmpDir, "vigile-worker")
	backupPath := execPath + ".previous"

	_ = os.WriteFile(execPath, []byte("new-broken-binary"), 0755)
	_ = os.WriteFile(backupPath, []byte("old-working-binary"), 0755)

	t.Run("CheckAndRollback performs rollback when timeout exceeded", func(t *testing.T) {
		testPendingPath := filepath.Join(tmpDir, "pending.json")
		PendingFilePath = testPendingPath
		defer func() { PendingFilePath = "/var/lib/vigile/update_pending.json" }()

		_ = os.WriteFile(testPendingPath, []byte(`{"previous_version":"1.0.0","new_version":"2.0.0","updated_at":"2020-01-01T00:00:00Z","confirmed":false}`), 0600)

		rolledBack, err := CheckAndRollbackIfFailed(execPath)
		if !rolledBack {
			t.Errorf("expected rollback to be performed")
		}
		if err == nil {
			t.Errorf("expected error message describing rollback")
		}

		data, _ := os.ReadFile(execPath)
		if string(data) != "old-working-binary" {
			t.Errorf("got execPath content %q, want %q", string(data), "old-working-binary")
		}
	})
}
