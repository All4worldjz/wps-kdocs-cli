package wpsclient

import (
	"crypto/md5"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestDigestTransport(t *testing.T) {
	username := "user"
	password := "pass"
	realm := "WPS-Realm"
	nonce := "dcd98b7102dd2f0e8b11d0f600bfb0c093"
	qop := "auth"
	opaque := "5ccc069c403ebaf9f0171e9517f40e41"

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if auth == "" {
			// Challenge with 401
			w.Header().Set("WWW-Authenticate", fmt.Sprintf(`Digest realm="%s", nonce="%s", qop="%s", opaque="%s"`, realm, nonce, qop, opaque))
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte("unauthorized"))
			return
		}

		// Verify auth header contains correct parameters
		if !strings.HasPrefix(auth, "Digest ") {
			t.Errorf("expected Digest auth header, got %s", auth)
			w.WriteHeader(http.StatusBadRequest)
			return
		}

		params := parseDigestHeader(auth[7:])
		if params["username"] != username || params["realm"] != realm || params["nonce"] != nonce || params["qop"] != qop || params["opaque"] != opaque {
			t.Errorf("incorrect digest params in request: %+v", params)
			w.WriteHeader(http.StatusUnauthorized)
			return
		}

		// Verify response hash calculation
		// HA1 = MD5("user:WPS-Realm:pass")
		h1 := md5.Sum([]byte(fmt.Sprintf("%s:%s:%s", username, realm, password)))
		ha1 := fmt.Sprintf("%x", h1)

		// HA2 = MD5("GET:/test")
		h2 := md5.Sum([]byte(fmt.Sprintf("%s:%s", r.Method, r.URL.Path)))
		ha2 := fmt.Sprintf("%x", h2)

		expectedResponse := fmt.Sprintf("%x", md5.Sum([]byte(fmt.Sprintf("%s:%s:%s:%s:%s:%s",
			ha1,
			nonce,
			params["nc"],
			params["cnonce"],
			qop,
			ha2,
		))))

		if params["response"] != expectedResponse {
			t.Errorf("expected response hash %s, got %s", expectedResponse, params["response"])
			w.WriteHeader(http.StatusForbidden)
			return
		}

		w.WriteHeader(http.StatusOK)
		w.Write([]byte("success"))
	}))
	defer server.Close()

	// Use custom DigestTransport
	transport := NewDigestTransport(username, password)
	client := &http.Client{Transport: transport}

	req, err := http.NewRequest("GET", server.URL+"/test", nil)
	if err != nil {
		t.Fatalf("failed to create request: %v", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		t.Fatalf("request failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Errorf("expected status 200, got %d", resp.StatusCode)
	}

	body, _ := io.ReadAll(resp.Body)
	if string(body) != "success" {
		t.Errorf("expected body success, got %q", string(body))
	}
}

func parseDigestHeader(header string) map[string]string {
	result := make(map[string]string)
	parts := strings.Split(header, ",")
	for _, part := range parts {
		kv := strings.SplitN(strings.TrimSpace(part), "=", 2)
		if len(kv) == 2 {
			k := kv[0]
			v := strings.Trim(kv[1], `"`)
			result[k] = v
		}
	}
	return result
}
