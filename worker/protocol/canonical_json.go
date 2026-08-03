package protocol

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"unicode/utf8"
)

// CanonicalizeJSON converts any JSON bytes or Go data structure into RFC 8785 (JCS) canonical JSON bytes.
// RFC 8785 specifies:
// 1. UTF-8 encoding without BOM
// 2. Object keys sorted lexicographically by UTF-8 bytes (code points)
// 3. No whitespace between tokens
// 4. Numbers formatted deterministically without trailing zeros or unneeded exponents
func CanonicalizeJSON(data []byte) ([]byte, error) {
	var val interface{}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(&val); err != nil {
		return nil, fmt.Errorf("canonicalize: invalid JSON: %w", err)
	}
	var buf bytes.Buffer
	if err := serializeJCS(&buf, val); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// SerializeValue converts any Go value into RFC 8785 canonical JSON bytes.
func SerializeValue(val interface{}) ([]byte, error) {
	var buf bytes.Buffer
	if err := serializeJCS(&buf, val); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func serializeJCS(buf *bytes.Buffer, val interface{}) error {
	switch v := val.(type) {
	case nil:
		buf.WriteString("null")
	case bool:
		if v {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
	case string:
		serializeString(buf, v)
	case json.Number:
		if err := serializeNumber(buf, v.String()); err != nil {
			return err
		}
	case float64:
		if err := serializeNumber(buf, strconv.FormatFloat(v, 'f', -1, 64)); err != nil {
			return err
		}
	case float32:
		if err := serializeNumber(buf, strconv.FormatFloat(float64(v), 'f', -1, 64)); err != nil {
			return err
		}
	case int:
		buf.WriteString(strconv.Itoa(v))
	case int64:
		buf.WriteString(strconv.FormatInt(v, 10))
	case uint64:
		buf.WriteString(strconv.FormatUint(v, 10))
	case map[string]interface{}:
		return serializeObject(buf, v)
	case []interface{}:
		return serializeArray(buf, v)
	default:
		// Attempt re-marshaling unknown struct or custom map via json package first
		b, err := json.Marshal(val)
		if err != nil {
			return fmt.Errorf("canonicalize: unmarshalable type %T: %w", val, err)
		}
		return serializeRawJSON(buf, b)
	}
	return nil
}

func serializeRawJSON(buf *bytes.Buffer, data []byte) error {
	var val interface{}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	if err := decoder.Decode(&val); err != nil {
		return err
	}
	return serializeJCS(buf, val)
}

func serializeObject(buf *bytes.Buffer, m map[string]interface{}) error {
	buf.WriteByte('{')
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys) // Lexicographical sort by UTF-8 bytes

	for i, k := range keys {
		if i > 0 {
			buf.WriteByte(',')
		}
		serializeString(buf, k)
		buf.WriteByte(':')
		if err := serializeJCS(buf, m[k]); err != nil {
			return err
		}
	}
	buf.WriteByte('}')
	return nil
}

func serializeArray(buf *bytes.Buffer, arr []interface{}) error {
	buf.WriteByte('[')
	for i, v := range arr {
		if i > 0 {
			buf.WriteByte(',')
		}
		if err := serializeJCS(buf, v); err != nil {
			return err
		}
	}
	buf.WriteByte(']')
	return nil
}

func serializeString(buf *bytes.Buffer, s string) {
	buf.WriteByte('"')
	for len(s) > 0 {
		r, size := utf8.DecodeRuneInString(s)
		s = s[size:]
		switch r {
		case '"':
			buf.WriteString(`\"`)
		case '\\':
			buf.WriteString(`\\`)
		case '\b':
			buf.WriteString(`\b`)
		case '\f':
			buf.WriteString(`\f`)
		case '\n':
			buf.WriteString(`\n`)
		case '\r':
			buf.WriteString(`\r`)
		case '\t':
			buf.WriteString(`\t`)
		default:
			if r < 0x20 {
				buf.WriteString(fmt.Sprintf(`\u%04x`, r))
			} else {
				buf.WriteRune(r)
			}
		}
	}
	buf.WriteByte('"')
}

func serializeNumber(buf *bytes.Buffer, rawNum string) error {
	// Parse as float64 to validate and format canonical representation
	f, err := strconv.ParseFloat(rawNum, 64)
	if err != nil {
		return fmt.Errorf("invalid number %q: %w", rawNum, err)
	}

	// RFC 8785 formatting rules for numbers
	// Integer numbers: format as integer if no decimal part
	if f == float64(int64(f)) && !bytes.ContainsAny([]byte(rawNum), ".eE") {
		buf.WriteString(strconv.FormatInt(int64(f), 10))
		return nil
	}

	// General float formatting
	formatted := strconv.FormatFloat(f, 'g', -1, 64)
	buf.WriteString(formatted)
	return nil
}
