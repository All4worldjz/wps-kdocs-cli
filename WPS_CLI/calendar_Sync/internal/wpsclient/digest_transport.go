package wpsclient

import (
	"crypto/md5"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"
	"sync"
)

type DigestTransport struct {
	Username  string
	Password  string
	Transport http.RoundTripper

	mu        sync.Mutex
	realm     string
	nonce     string
	qop       string
	opaque    string
	algorithm string
	nc        int
}

func NewDigestTransport(username, password string) *DigestTransport {
	return &DigestTransport{
		Username:  username,
		Password:  password,
		Transport: http.DefaultTransport,
	}
}

func (t *DigestTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	t.mu.Lock()
	nonce := t.nonce
	t.mu.Unlock()

	var authHeader string
	if nonce != "" {
		authHeader = t.makeAuthHeader(req.Method, req.URL.RequestURI())
	}

	var reqWithAuth *http.Request
	if authHeader != "" {
		reqWithAuth = req.Clone(req.Context())
		reqWithAuth.Header.Set("Authorization", authHeader)
	} else {
		reqWithAuth = req
	}

	resp, err := t.Transport.RoundTrip(reqWithAuth)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode == http.StatusUnauthorized {
		authW := resp.Header.Get("WWW-Authenticate")
		if strings.HasPrefix(authW, "Digest ") {
			resp.Body.Close() // Close previous unauthorized body

			t.mu.Lock()
			t.parseChallenge(authW[7:])
			t.mu.Unlock()

			retryAuthHeader := t.makeAuthHeader(req.Method, req.URL.RequestURI())
			reqRetry := req.Clone(req.Context())
			reqRetry.Header.Set("Authorization", retryAuthHeader)
			if req.GetBody != nil {
				body, err := req.GetBody()
				if err == nil {
					reqRetry.Body = body
				}
			}

			return t.Transport.RoundTrip(reqRetry)
		}
	}

	return resp, nil
}

func (t *DigestTransport) parseChallenge(challenge string) {
	params := make(map[string]string)
	parts := strings.Split(challenge, ",")
	for _, part := range parts {
		kv := strings.SplitN(strings.TrimSpace(part), "=", 2)
		if len(kv) == 2 {
			k := kv[0]
			v := strings.Trim(kv[1], `"`)
			params[k] = v
		}
	}

	t.realm = params["realm"]
	t.nonce = params["nonce"]
	t.qop = params["qop"]
	t.opaque = params["opaque"]
	t.algorithm = params["algorithm"]
	t.nc = 0 // Reset nonce count for new nonce
}

func (t *DigestTransport) makeAuthHeader(method, uri string) string {
	t.mu.Lock()
	defer t.mu.Unlock()

	t.nc++
	ncStr := fmt.Sprintf("%08x", t.nc)

	// Random cnonce
	b := make([]byte, 8)
	_, _ = rand.Read(b)
	cnonce := hex.EncodeToString(b)

	// Calculate response
	// HA1 = MD5(username:realm:password)
	h1 := md5.Sum([]byte(fmt.Sprintf("%s:%s:%s", t.Username, t.realm, t.Password)))
	ha1 := fmt.Sprintf("%x", h1)

	// HA2 = MD5(method:uri)
	h2 := md5.Sum([]byte(fmt.Sprintf("%s:%s", method, uri)))
	ha2 := fmt.Sprintf("%x", h2)

	var response string
	if t.qop == "auth" || t.qop == "auth-int" {
		response = fmt.Sprintf("%x", md5.Sum([]byte(fmt.Sprintf("%s:%s:%s:%s:%s:%s",
			ha1,
			t.nonce,
			ncStr,
			cnonce,
			t.qop,
			ha2,
		))))
	} else {
		response = fmt.Sprintf("%x", md5.Sum([]byte(fmt.Sprintf("%s:%s:%s",
			ha1,
			t.nonce,
			ha2,
		))))
	}

	authVal := fmt.Sprintf(`Digest username="%s", realm="%s", nonce="%s", uri="%s", response="%s"`,
		t.Username, t.realm, t.nonce, uri, response)

	if t.opaque != "" {
		authVal += fmt.Sprintf(`, opaque="%s"`, t.opaque)
	}
	if t.qop != "" {
		authVal += fmt.Sprintf(`, qop="%s", nc=%s, cnonce="%s"`, t.qop, ncStr, cnonce)
	}
	if t.algorithm != "" {
		authVal += fmt.Sprintf(`, algorithm="%s"`, t.algorithm)
	}

	return authVal
}
