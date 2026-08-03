package protocol

import (
	"bytes"
	"testing"
)

func TestCanonicalizeJSON(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected string
	}{
		{
			name:     "Sorted object keys",
			input:    `{"b": 2, "a": 1, "c": 3}`,
			expected: `{"a":1,"b":2,"c":3}`,
		},
		{
			name:     "Nested objects sorting",
			input:    `{"z": {"y": true, "x": false}, "a": [3, 2, 1]}`,
			expected: `{"a":[3,2,1],"z":{"x":false,"y":true}}`,
		},
		{
			name:     "Whitespace removal",
			input:    "{\n  \"name\" : \"vigile\" ,\n  \"version\" : 2\n}",
			expected: `{"name":"vigile","version":2}`,
		},
		{
			name:     "Escaped characters",
			input:    `{"msg": "hello\nworld\ttab"}`,
			expected: `{"msg":"hello\nworld\ttab"}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := CanonicalizeJSON([]byte(tt.input))
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if !bytes.Equal(got, []byte(tt.expected)) {
				t.Errorf("CanonicalizeJSON() = %s, want %s", string(got), tt.expected)
			}
		})
	}
}
