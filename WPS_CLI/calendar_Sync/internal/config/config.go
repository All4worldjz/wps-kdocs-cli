package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	WPS    WPSConfig    `yaml:"wps"`
	Proxy  ProxyConfig  `yaml:"proxy"`
	Cache  CacheConfig  `yaml:"cache"`
	Poller PollerConfig `yaml:"poller"`
}

type WPSConfig struct {
	ServerURL string `yaml:"server_url"`
	Username  string `yaml:"username"`
	Password  string `yaml:"password"`
}

type ProxyConfig struct {
	ListenAddr string `yaml:"listen_addr"`
	ProxyUser  string `yaml:"proxy_user"`
	ProxyPass  string `yaml:"proxy_pass"`
}

type CacheConfig struct {
	DBPath string `yaml:"db_path"`
}

type PollerConfig struct {
	IntervalSeconds int  `yaml:"interval_seconds"`
	Enabled         bool `yaml:"enabled"`
}

func DefaultConfig() *Config {
	return &Config{
		WPS: WPSConfig{
			ServerURL: "https://caldav.wps.cn",
			Username:  "",
			Password:  "",
		},
		Proxy: ProxyConfig{
			ListenAddr: "127.0.0.1:8843",
			ProxyUser:  "caldav",
			ProxyPass:  "",
		},
		Cache: CacheConfig{
			DBPath: "data/cache.db",
		},
		Poller: PollerConfig{
			IntervalSeconds: 60,
			Enabled:         true,
		},
	}
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	cfg := DefaultConfig()
	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	if err := cfg.Validate(); err != nil {
		return nil, fmt.Errorf("validate config: %w", err)
	}

	return cfg, nil
}

func (c *Config) Validate() error {
	if c.WPS.ServerURL == "" {
		return fmt.Errorf("wps.server_url is required")
	}
	if c.WPS.Username == "" {
		return fmt.Errorf("wps.username is required")
	}
	if c.WPS.Password == "" {
		return fmt.Errorf("wps.password is required")
	}
	if c.Proxy.ListenAddr == "" {
		return fmt.Errorf("proxy.listen_addr is required")
	}
	if c.Proxy.ProxyUser == "" {
		return fmt.Errorf("proxy.proxy_user is required")
	}
	if c.Proxy.ProxyPass == "" {
		return fmt.Errorf("proxy.proxy_pass is required")
	}
	if c.Cache.DBPath == "" {
		return fmt.Errorf("cache.db_path is required")
	}
	if c.Poller.IntervalSeconds < 10 {
		return fmt.Errorf("poller.interval_seconds must be >= 10")
	}
	return nil
}
