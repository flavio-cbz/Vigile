package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"time"
)

const dockerSocket = "/var/run/docker.sock"

// dockerClient is an HTTP client that talks to the Docker daemon via Unix socket.
var dockerClient = &http.Client{
	Transport: &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			var d net.Dialer
			return d.DialContext(ctx, "unix", dockerSocket)
		},
	},
	Timeout: 30 * time.Second,
}

func dockerAPI(method, path string, body io.Reader) ([]byte, error) {
	if _, err := os.Stat(dockerSocket); os.IsNotExist(err) {
		return nil, fmt.Errorf("Docker socket not found at %s", dockerSocket)
	}
	req, err := http.NewRequest(method, "http://localhost"+path, body)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := dockerClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("Docker API call failed: %v", err)
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("Docker API error %d: %s", resp.StatusCode, string(data))
	}
	return data, nil
}

func handleListContainers(intent Intent) IntentResult {
	data, err := dockerAPI("GET", "/v1.45/containers/json?all=true", nil)
	if err != nil {
		return IntentResult{Success: false, Error: err.Error()}
	}

	var containers []map[string]interface{}
	if err := json.Unmarshal(data, &containers); err != nil {
		return IntentResult{Success: false, Error: fmt.Sprintf("parse error: %v", err)}
	}

	// Extract just the fields we need
	type containerSummary struct {
		ID    string   `json:"id"`
		Name  string   `json:"name"`
		Image string   `json:"image"`
		State string   `json:"state"`
		Ports []string `json:"ports,omitempty"`
	}
	var summary []containerSummary
	for _, c := range containers {
		id, _ := c["Id"].(string)
		if len(id) > 12 {
			id = id[:12]
		}
		state, _ := c["State"].(string)
		image, _ := c["Image"].(string)
		names, _ := c["Names"].([]interface{})
		name := ""
		if len(names) > 0 {
			name, _ = names[0].(string)
			name = strings.TrimPrefix(name, "/")
		}
		portsRaw, _ := c["Ports"].([]interface{})
		var ports []string
		for _, p := range portsRaw {
			if pm, ok := p.(map[string]interface{}); ok {
				privatePort, _ := pm["PrivatePort"].(float64)
				publicPort, hasPublic := pm["PublicPort"]
				if hasPublic {
					ip, _ := pm["IP"].(string)
					ports = append(ports, fmt.Sprintf("%s:%v->%.0f", ip, publicPort, privatePort))
				} else {
					ports = append(ports, fmt.Sprintf("%.0f", privatePort))
				}
			}
		}
		summary = append(summary, containerSummary{
			ID: id, Name: name, Image: image, State: state, Ports: ports,
		})
	}

	out, _ := json.Marshal(summary)
	return IntentResult{Success: true, Output: string(out)}
}

func handleRestartContainer(intent Intent) IntentResult {
	if intent.RequestedBy == "" {
		return IntentResult{Success: false, Error: "missing requested_by context"}
	}
	containerID := getParamString(intent.Params, "container_id", "")
	approvalID := getParamString(intent.Params, "approval_id", "")
	log.Printf("executing action action=RESTART_CONTAINER container_id=%s node_id=%s requested_by=%s approval_id=%s intent_id=%s",
		containerID, nodeID, intent.RequestedBy, approvalID, intent.IntentID)

	if containerID == "" {
		return IntentResult{Success: false, Error: "container_id parameter required"}
	}

	_, err := dockerAPI("POST", fmt.Sprintf("/v1.45/containers/%s/restart", containerID), nil)
	if err != nil {
		return IntentResult{Success: false, Error: err.Error()}
	}
	return IntentResult{Success: true, Output: fmt.Sprintf("Container %s restarted", containerID)}
}
