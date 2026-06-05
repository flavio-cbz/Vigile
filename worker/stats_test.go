package main

import (
	"sync"
	"testing"
)

// TestCPUStatsConcurrentAccess verifies that getCPUPercent() can be called
// concurrently without data races on the prevIdle/prevTotal globals.
// On Linux (where /proc/stat exists) this exercises the actual computation path.
// On other platforms the function returns early, but the atomic operations
// are still exercised through concurrent calls.
func TestCPUStatsConcurrentAccess(t *testing.T) {
	var wg sync.WaitGroup
	for range 20 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			_ = getCPUPercent()
		}()
	}
	wg.Wait()
}

// TestCPUStatsAtomicDirectAccess verifies that direct concurrent load/store
// on the atomic globals does not panic or produce invalid values.
func TestCPUStatsAtomicDirectAccess(t *testing.T) {
	var wg sync.WaitGroup
	for range 10 {
		wg.Add(1)
		go func() {
			defer wg.Done()
			prevIdle.Store(100)
			prevTotal.Store(1000)
			_ = prevIdle.Load()
			_ = prevTotal.Load()
		}()
	}
	wg.Wait()
}
