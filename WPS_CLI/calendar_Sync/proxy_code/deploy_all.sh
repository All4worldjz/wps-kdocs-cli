#!/bin/bash
# One-shot deploy script — run this when SSH to VPS is available
# Usage: bash deploy_all.sh

set -e

echo "=== WPS CalDAV Proxy — Full Deploy ==="
echo ""

# 1. Upload fixed wpsclient
echo "[1/6] Uploading fixed wpsclient..."
scp wpsclient_v2.go admin@all4world.cc:/opt/wps-caldav-proxy/internal/wpsclient/client.go

# 2. Fix sed on remaining namespace issues
echo "[2/6] Applying namespace fixes..."
ssh admin@all4world.cc '
sed -i "s|(?i)<href|(?i)<[^>]*:href|g" /opt/wps-caldav-proxy/internal/wpsclient/client.go 2>/dev/null
sed -i "s|(?i)<response>|(?i)<[^>]*:response>|g" /opt/wps-caldav-proxy/internal/wpsclient/client.go 2>/dev/null
echo "sed done"
'

# 3. Rebuild
echo "[3/6] Rebuilding..."
ssh admin@all4world.cc 'cd /opt/wps-caldav-proxy && rm -f data/cache.db && go build -o wps-caldav-proxy ./cmd/wps-caldav-proxy/ 2>&1 && echo "BUILD OK"'

# 4. Quick test
echo "[4/6] Testing..."
ssh admin@all4world.cc '
cd /opt/wps-caldav-proxy && rm -f data/cache.db
timeout 20 ./wps-caldav-proxy -config config.yaml 2>&1 &
PID=$!
sleep 10

echo "--- OPTIONS ---"
curl -s -u "caldav:CHANGE_ME_PASSWORD" -X OPTIONS http://127.0.0.1:8843/ -D- 2>&1 | head -5

echo "--- PROPFIND ---"
curl -s -u "caldav:CHANGE_ME_PASSWORD" -X PROPFIND "http://127.0.0.1:8843/" -H "Content-Type: text/xml" -d "<?xml version=\"1.0\"?><D:propfind xmlns:D=\"DAV:\"><D:prop><D:current-user-principal/></D:prop></D:propfind>" 2>&1 | head -5

echo "--- Events ---"
curl -s -u "caldav:CHANGE_ME_PASSWORD" -X REPORT "http://127.0.0.1:8843/u/caldav/default/" -H "Content-Type: text/xml" -d "<?xml version=\"1.0\"?><C:calendar-query xmlns:D=\"DAV:\" xmlns:C=\"urn:ietf:params:xml:ns:caldav\"><D:prop><D:getetag/></D:prop><C:filter><C:comp-filter name=\"VCALENDAR\"><C:comp-filter name=\"VEVENT\"/></C:comp-filter></C:filter></C:calendar-query>" 2>&1 | head -10

kill $PID 2>/dev/null
wait $PID 2>/dev/null
echo "Test complete"
'

# 5. Nginx config reminder
echo ""
echo "[5/6] Nginx configuration"
echo "  Add to /home/admin/workshop/nginx-conf/www.conf:"
echo ""
echo '  location /caldav/ {'
echo '      proxy_pass http://127.0.0.1:8843/;'
echo '      proxy_set_header Host $host;'
echo '      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;'
echo '      proxy_pass_request_headers on;'
echo '      proxy_buffering off;'
echo '  }'
echo ""
echo "  Then: docker exec webserver nginx -s reload"
echo ""

# 6. systemd
echo "[6/6] Install systemd service"
echo "  sudo cp deploy/wps-caldav-proxy.service /etc/systemd/system/"
echo "  sudo systemctl enable --now wps-caldav-proxy"
echo ""
echo "=== Client Configuration ==="
echo "  Server:   https://www.all4world.cc/caldav"
echo "  Username: caldav"
echo "  Password: CHANGE_ME_PASSWORD (set in config.yaml)"
echo "  Port:     443"
echo "  SSL:      Yes"