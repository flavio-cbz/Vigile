package main

import (
	"testing"
)

func TestGetParamString(t *testing.T) {
	t.Run("nil params returns default", func(t *testing.T) {
		got := getParamString(nil, "key", "default")
		if got != "default" {
			t.Errorf("getParamString(nil, \"key\", \"default\") = %q, want %q", got, "default")
		}
	})

	t.Run("missing key returns default", func(t *testing.T) {
		params := map[string]interface{}{"other": "value"}
		got := getParamString(params, "key", "default")
		if got != "default" {
			t.Errorf("getParamString with missing key = %q, want %q", got, "default")
		}
	})

	t.Run("string value returns it", func(t *testing.T) {
		params := map[string]interface{}{"name": "test-node"}
		got := getParamString(params, "name", "default")
		if got != "test-node" {
			t.Errorf("getParamString = %q, want %q", got, "test-node")
		}
	})

	t.Run("non-string value returns default", func(t *testing.T) {
		params := map[string]interface{}{"count": 42}
		got := getParamString(params, "count", "default")
		if got != "default" {
			t.Errorf("getParamString with int value = %q, want %q", got, "default")
		}
	})

	t.Run("empty string value returns empty string", func(t *testing.T) {
		params := map[string]interface{}{"name": ""}
		got := getParamString(params, "name", "default")
		if got != "" {
			t.Errorf("getParamString with empty string = %q, want empty", got)
		}
	})
}

func TestGetParamInt(t *testing.T) {
	t.Run("nil params returns default", func(t *testing.T) {
		got := getParamInt(nil, "key", 99)
		if got != 99 {
			t.Errorf("getParamInt(nil, \"key\", 99) = %d, want %d", got, 99)
		}
	})

	t.Run("missing key returns default", func(t *testing.T) {
		params := map[string]interface{}{"other": "value"}
		got := getParamInt(params, "key", 99)
		if got != 99 {
			t.Errorf("getParamInt with missing key = %d, want %d", got, 99)
		}
	})

	t.Run("float64 value returns int", func(t *testing.T) {
		params := map[string]interface{}{"port": 8080.0}
		got := getParamInt(params, "port", 0)
		if got != 8080 {
			t.Errorf("getParamInt with float64 = %d, want %d", got, 8080)
		}
	})

	t.Run("int value returns int", func(t *testing.T) {
		params := map[string]interface{}{"count": 42}
		got := getParamInt(params, "count", 0)
		if got != 42 {
			t.Errorf("getParamInt with int = %d, want %d", got, 42)
		}
	})

	t.Run("int64 value returns int", func(t *testing.T) {
		params := map[string]interface{}{"count": int64(999)}
		got := getParamInt(params, "count", 0)
		if got != 999 {
			t.Errorf("getParamInt with int64 = %d, want %d", got, 999)
		}
	})

	t.Run("non-numeric value returns default", func(t *testing.T) {
		params := map[string]interface{}{"port": "string"}
		got := getParamInt(params, "port", 0)
		if got != 0 {
			t.Errorf("getParamInt with string = %d, want %d", got, 0)
		}
	})

	t.Run("zero value for existing key returns 0", func(t *testing.T) {
		params := map[string]interface{}{"count": 0}
		got := getParamInt(params, "count", 99)
		if got != 0 {
			t.Errorf("getParamInt with zero = %d, want %d", got, 0)
		}
	})
}
