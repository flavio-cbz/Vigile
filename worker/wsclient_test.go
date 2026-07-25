package main

import (
	"bufio"
	"bytes"
	"testing"
)

func TestComputeAcceptKeyUsesRFCMagicGUID(t *testing.T) {
	got := computeAcceptKey("dGhlIHNhbXBsZSBub25jZQ==")
	want := "s3pPLMBiTxaQ9kYGzzhZRbK+xOo="
	if got != want {
		t.Fatalf("unexpected accept key: got %q want %q", got, want)
	}
}

func TestReadFrameRejectsInvalidHugeLength(t *testing.T) {
	frame := []byte{
		0x81,
		0x7f,
		0x80, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
	}
	ws := &WSConn{reader: bufio.NewReader(bytes.NewReader(frame))}

	if _, _, err := ws.readFrame(); err == nil {
		t.Fatal("expected invalid 64-bit payload length error")
	}
}
