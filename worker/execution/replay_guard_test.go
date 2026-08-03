package execution

import (
	"testing"
	"time"
)

func TestReplayGuard(t *testing.T) {
	rg := NewReplayGuard(3, 100*time.Millisecond)

	t.Run("First occurrence is not replayed", func(t *testing.T) {
		if rg.IsReplayed("req-1", time.Now().Add(time.Hour)) {
			t.Errorf("req-1 should not be replayed on first call")
		}
	})

	t.Run("Second occurrence is detected as replayed", func(t *testing.T) {
		if !rg.IsReplayed("req-1", time.Now().Add(time.Hour)) {
			t.Errorf("req-1 should be detected as replayed on second call")
		}
	})

	t.Run("Expired entry is purged and allowed again", func(t *testing.T) {
		rgShort := NewReplayGuard(10, 10*time.Millisecond)
		rgShort.IsReplayed("req-expire", time.Now().Add(10*time.Millisecond))
		time.Sleep(20 * time.Millisecond)
		if rgShort.IsReplayed("req-expire", time.Now().Add(time.Hour)) {
			t.Errorf("req-expire should not be marked replayed after TTL expiration")
		}
	})
}
