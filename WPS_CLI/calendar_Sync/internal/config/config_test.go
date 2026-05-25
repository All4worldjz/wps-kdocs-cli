package config

import (
	"os"
	"testing"
)

func TestConfigLoadAndValidate(t *testing.T) {
	// Test Case 1: Load a valid config
	validYAML := []byte(`
wps:
  server_url: "https://caldav.wps.cn"
  username: "user123"
  password: "wpspassword"
proxy:
  listen_addr: "127.0.0.1:8843"
  proxy_user: "caldav"
  proxy_pass: "proxypass"
cache:
  db_path: "data/cache.db"
poller:
  interval_seconds: 30
  enabled: true
`)

	tmpFile, err := os.CreateTemp("", "config_*.yaml")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	defer os.Remove(tmpFile.Name())

	if _, err := tmpFile.Write(validYAML); err != nil {
		t.Fatalf("failed to write config file: %v", err)
	}
	tmpFile.Close()

	cfg, err := Load(tmpFile.Name())
	if err != nil {
		t.Fatalf("failed to load valid config: %v", err)
	}

	if cfg.WPS.Username != "user123" {
		t.Errorf("expected wps.username to be user123, got %s", cfg.WPS.Username)
	}
	if cfg.Poller.IntervalSeconds != 30 {
		t.Errorf("expected poller.interval_seconds to be 30, got %d", cfg.Poller.IntervalSeconds)
	}

	// Test Case 2: Validation errors for missing fields
	invalidYAML := []byte(`
wps:
  server_url: "https://caldav.wps.cn"
  username: ""
  password: "wpspassword"
`)
	tmpFileInvalid, err := os.CreateTemp("", "config_invalid_*.yaml")
	if err != nil {
		t.Fatalf("failed to create temp file: %v", err)
	}
	defer os.Remove(tmpFileInvalid.Name())

	if _, err := tmpFileInvalid.Write(invalidYAML); err != nil {
		t.Fatalf("failed to write config file: %v", err)
	}
	tmpFileInvalid.Close()

	_, err = Load(tmpFileInvalid.Name())
	if err == nil {
		t.Error("expected error loading invalid config, got nil")
	}
}
