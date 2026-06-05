package main

import (
	"bufio"
	"crypto/rand"
	"crypto/sha1" //nolint:gosec // required for RFC 6455
	"crypto/tls"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"net"
	"net/url"
	"strings"
	"sync"
	"time"
)

// httpReadResponse reads an HTTP response manually from a reader.
// We avoid net/http.ReadResponse because it can behave unexpectedly
// with 101 Switching Protocols responses (WebSocket upgrade).
func httpReadResponse(r *bufio.Reader) (int, map[string]string, error) {
	headers := make(map[string]string)

	// Read status line
	statusLine, err := r.ReadString('\n')
	if err != nil {
		return 0, nil, fmt.Errorf("ws: read status: %w", err)
	}
	statusLine = strings.TrimRight(statusLine, "\r\n")

	var proto string
	var statusCode int
	if _, err := fmt.Sscanf(statusLine, "%s %d", &proto, &statusCode); err != nil {
		return 0, nil, fmt.Errorf("ws: parse status %q: %w", statusLine, err)
	}

	// Read headers
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			return 0, nil, fmt.Errorf("ws: read header: %w", err)
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			break // end of headers
		}
		parts := strings.SplitN(line, ":", 2)
		if len(parts) == 2 {
			key := strings.TrimSpace(parts[0])
			value := strings.TrimSpace(parts[1])
			headers[key] = value
		}
	}

	return statusCode, headers, nil
}

// ---------------------------------------------------------------------------
// RFC 6455 WebSocket client — zero external dependencies
// ---------------------------------------------------------------------------

const (
	opText   = 0x1
	opClose  = 0x8
	opPing   = 0x9
	opPong   = 0xA

	wsMagicGUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
)

// WSConn wraps a net.Conn after WebSocket upgrade.
type WSConn struct {
	conn   net.Conn
	reader *bufio.Reader
	mu     sync.Mutex // protects writes + close
	closed bool
}

// DialWebSocket performs the WebSocket handshake and returns an upgraded connection.
func DialWebSocket(rawURL string) (*WSConn, error) {
	u, err := url.Parse(rawURL)
	if err != nil {
		return nil, fmt.Errorf("ws: invalid URL %q: %w", rawURL, err)
	}

	// Build WebSocket key
	key := make([]byte, 16)
	if _, err := rand.Read(key); err != nil {
		return nil, fmt.Errorf("ws: random key: %w", err)
	}
	wsKey := base64.StdEncoding.EncodeToString(key)

	// Connect TCP
	host := u.Host
	if !strings.Contains(host, ":") {
		if u.Scheme == "wss" || u.Scheme == "https" {
			host += ":443"
		} else {
			host += ":80"
		}
	}

	var dialer net.Dialer
	dialer.Timeout = 10 * time.Second

	var conn net.Conn
	if u.Scheme == "wss" || u.Scheme == "https" {
		conn, err = tls.DialWithDialer(&dialer, "tcp", host, &tls.Config{ServerName: u.Hostname(), MinVersion: tls.VersionTLS12})
	} else {
		conn, err = dialer.Dial("tcp", host)
	}
	if err != nil {
		return nil, fmt.Errorf("ws: dial %s: %w", host, err)
	}

	// Send HTTP upgrade request
	path := u.Path
	if u.RawQuery != "" {
		path += "?" + u.RawQuery
	}
	req := fmt.Sprintf("GET %s HTTP/1.1\r\nHost: %s\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n",
		path, u.Host, wsKey)

	if _, err := conn.Write([]byte(req)); err != nil {
		conn.Close()
		return nil, fmt.Errorf("ws: write upgrade: %w", err)
	}

	// Parse HTTP response manually — reuse the same buffered reader
	// for both HTTP headers and subsequent WebSocket frames.
	reader := bufio.NewReader(conn)
	statusCode, headers, err := httpReadResponse(reader)
	if err != nil {
		conn.Close()
		return nil, fmt.Errorf("ws: read response: %w", err)
	}

	if statusCode != 101 {
		conn.Close()
		return nil, fmt.Errorf("ws: expected 101, got %d", statusCode)
	}

	if headers["Sec-WebSocket-Accept"] != computeAcceptKey(wsKey) {
		conn.Close()
		return nil, errors.New("ws: invalid Sec-WebSocket-Accept")
	}

	return &WSConn{
		conn:   conn,
		reader: reader,
	}, nil
}

// computeAcceptKey computes the RFC 6455 Sec-WebSocket-Accept value.
func computeAcceptKey(key string) string {
	h := sha1.Sum([]byte(key + wsMagicGUID))
	return base64.StdEncoding.EncodeToString(h[:])
}

// ── Frame I/O ──────────────────────────────────────────────────────────────

// WriteText sends a text frame (masked, as required by RFC 6455 for clients).
func (ws *WSConn) WriteText(data []byte) error {
	ws.mu.Lock()
	defer ws.mu.Unlock()
	if ws.closed {
		return errors.New("ws: connection closed")
	}
	return ws.writeFrame(opText, data)
}

func (ws *WSConn) writeFrame(opcode byte, payload []byte) error {
	// Frame header
	// FIN=1, opcode, MASK=1, payload length
	header := []byte{0x80 | opcode}

	// Masking key (4 bytes, required for client frames)
	maskKey := make([]byte, 4)
	if _, err := rand.Read(maskKey); err != nil {
		return fmt.Errorf("ws: mask key: %w", err)
	}

	length := len(payload)
	if length <= 125 {
		header = append(header, byte(length)|0x80) // MASK bit set
	} else if length <= 65535 {
		header = append(header, 126|0x80)
		header = binary.BigEndian.AppendUint16(header, uint16(length))
	} else {
		header = append(header, 127|0x80)
		header = binary.BigEndian.AppendUint64(header, uint64(length))
	}

	header = append(header, maskKey...)

	// Apply mask to payload
	masked := make([]byte, length)
	for i, b := range payload {
		masked[i] = b ^ maskKey[i%4]
	}

	frame := append(header, masked...)
	_, err := ws.conn.Write(frame)
	return err
}

// ReadText reads a text frame (or handles control frames transparently).
func (ws *WSConn) ReadText() ([]byte, error) {
	for {
		opcode, payload, err := ws.readFrame()
		if err != nil {
			return nil, err
		}

		switch opcode {
		case opText:
			return payload, nil
		case opPing:
			// Respond with Pong automatically
			ws.mu.Lock()
			_ = ws.writeFrame(opPong, payload)
			ws.mu.Unlock()
		case opClose:
			_ = ws.Close()
			return nil, errors.New("ws: peer closed connection")
		case opPong:
			// ignore
		}
	}
}

func (ws *WSConn) readFrame() (opcode byte, payload []byte, err error) {
	// FIN + RSV + opcode
	header := make([]byte, 2)
	if _, err := io.ReadFull(ws.reader, header); err != nil {
		return 0, nil, fmt.Errorf("ws: read header: %w", err)
	}

	opcode = header[0] & 0x0F
	// fin := header[0]&0x80 != 0 (we assume single frames for simplicity)

	// Validate RSV bits (MUST be 0 per RFC 6455)
	if header[0]&0x70 != 0 {
		return 0, nil, errors.New("ws: invalid RSV bits")
	}

	masked := header[1]&0x80 != 0
	length := uint64(header[1] & 0x7F)

	switch {
	case length == 126:
		ext := make([]byte, 2)
		if _, err := io.ReadFull(ws.reader, ext); err != nil {
			return 0, nil, fmt.Errorf("ws: read ext length 16: %w", err)
		}
		length = uint64(binary.BigEndian.Uint16(ext))
	case length == 127:
		ext := make([]byte, 8)
		if _, err := io.ReadFull(ws.reader, ext); err != nil {
			return 0, nil, fmt.Errorf("ws: read ext length 64: %w", err)
		}
		length = binary.BigEndian.Uint64(ext)
		if length&(1<<63) != 0 {
			return 0, nil, errors.New("ws: invalid 64-bit payload length")
		}
	}

	var maskKey [4]byte
	if masked {
		if _, err := io.ReadFull(ws.reader, maskKey[:]); err != nil {
			return 0, nil, fmt.Errorf("ws: read mask key: %w", err)
		}
	}

	// Security: limit frame size to 1MB
	if length > 1_048_576 {
		return 0, nil, fmt.Errorf("ws: frame too large: %d bytes", length)
	}

	payload = make([]byte, length)
	if _, err := io.ReadFull(ws.reader, payload); err != nil {
		return 0, nil, fmt.Errorf("ws: read payload: %w", err)
	}

	if masked {
		for i, b := range payload {
			payload[i] = b ^ maskKey[i%4]
		}
	}

	return opcode, payload, nil
}

// Close sends a WebSocket close frame and closes the TCP connection.
func (ws *WSConn) Close() error {
	ws.mu.Lock()
	defer ws.mu.Unlock()
	if ws.closed {
		return nil
	}
	ws.closed = true
	// Best-effort close frame
	_ = ws.writeFrame(opClose, []byte{0x03, 0xE8}) // 1000 normal
	return ws.conn.Close()
}

// SetReadDeadline sets the read deadline on the underlying connection.
func (ws *WSConn) SetReadDeadline(t time.Time) error {
	return ws.conn.SetReadDeadline(t)
}
