package main

import (
	"bufio"
	"bytes"
	"net"
	"testing"
	"time"
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

func TestWSConnCloseInstantUnblock(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen failed: %v", err)
	}
	defer ln.Close()

	serverConnCh := make(chan net.Conn, 1)
	go func() {
		c, err := ln.Accept()
		if err == nil {
			serverConnCh <- c
		}
	}()

	clientConn, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatalf("dial failed: %v", err)
	}
	serverConn := <-serverConnCh
	defer serverConn.Close()

	ws := &WSConn{
		conn:   clientConn,
		reader: bufio.NewReader(clientConn),
	}

	readDone := make(chan struct{})
	go func() {
		_, _ = ws.ReadText()
		close(readDone)
	}()

	start := time.Now()
	if err := ws.Close(); err != nil {
		t.Fatalf("ws.Close() failed: %v", err)
	}

	select {
	case <-readDone:
		dur := time.Since(start)
		if dur > 50*time.Millisecond {
			t.Errorf("Close took too long to unblock reader: %v", dur)
		}
	case <-time.After(500 * time.Millisecond):
		t.Fatal("Close() failed to unblock ReadText in time")
	}

	// Writing to closed connection must fail immediately
	err = ws.WriteTextWithTimeout([]byte("hello"), 100*time.Millisecond)
	if err == nil {
		t.Fatal("expected error writing to closed WSConn")
	}
}

func TestWSConnCloseWhileLocked(t *testing.T) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen failed: %v", err)
	}
	defer ln.Close()

	clientConn, err := net.Dial("tcp", ln.Addr().String())
	if err != nil {
		t.Fatalf("dial failed: %v", err)
	}

	ws := &WSConn{
		conn:   clientConn,
		reader: bufio.NewReader(clientConn),
	}

	// Artificially hold ws.mu (simulating in-flight or blocked write)
	ws.mu.Lock()
	defer ws.mu.Unlock()

	start := time.Now()
	if err := ws.Close(); err != nil {
		t.Fatalf("ws.Close() failed: %v", err)
	}
	dur := time.Since(start)
	if dur > 50*time.Millisecond {
		t.Errorf("Close took too long while ws.mu was locked: %v", dur)
	}
}
