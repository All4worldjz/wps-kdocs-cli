#!/bin/bash
set -e

echo "=== WPS CalDAV Proxy Deploy ==="
echo ""

PROXY_DIR="/opt/wps-caldav-proxy"

# 1. Install Go dependencies
echo "[1/6] Installing Go dependencies..."
cd "$PROXY_DIR"
go mod tidy 2>&1 | tail -1

# 2. Build
echo "[2/6] Building..."
go build -o wps-caldav-proxy ./cmd/wps-caldav-proxy/
echo "  Binary: $PROXY_DIR/wps-caldav-proxy"

# 3. Test WPS connection
echo "[3/6] Testing WPS connection..."
# Run a quick check (timeout 10s)
timeout 15 "$PROXY_DIR/wps-caldav-proxy" -config "$PROXY_DIR/config.yaml" &
PID=$!
sleep 5

# Test connectivity
if curl -s -u "caldav:CHANGE_ME_PASSWORD" -X OPTIONS http://127.0.0.1:8843/ | grep -q "calendar-access"; then
    echo "  WPS CalDAV Proxy is running correctly!"
else
    echo "  ERROR: Proxy failed to start. Check logs."
fi

kill $PID 2>/dev/null
wait $PID 2>/dev/null

# 4. Install systemd service
echo "[4/6] Installing systemd service..."
sudo cp deploy/wps-caldav-proxy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wps-caldav-proxy

# 5. Start service
echo "[5/6] Starting service..."
sudo systemctl start wps-caldav-proxy
sleep 2
sudo systemctl status wps-caldav-proxy --no-pager | head -10

# 6. Configure Nginx
echo ""
echo "[6/6] Nginx configuration"
echo "  Add the following to your Nginx configuration (/home/admin/workshop/nginx-conf/www.conf):"
echo ""
echo '  location /caldav/ {'
echo '      proxy_pass http://127.0.0.1:8843/;'
echo '      proxy_set_header Host $host;'
echo '      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;'
echo '      proxy_set_header X-Real-IP $remote_addr;'
echo '      proxy_pass_request_headers on;'
echo '      proxy_buffering off;'
echo '  }'
echo ""
echo "  Then reload Nginx:"
echo "    docker exec webserver nginx -s reload"
echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Client configuration:"
echo "  Server:   https://www.all4world.cc/caldav"
echo "  Username: caldav"
echo "  Password: <password from config.yaml>"
echo "  Port:     443"
echo "  SSL:      Yes"