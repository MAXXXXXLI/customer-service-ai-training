#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  printf 'run as root\n' >&2
  exit 1
fi

public_mode=private
if [[ $# -eq 1 && $1 == --anonymous ]]; then
  public_mode=anonymous
elif [[ $# -ne 0 ]]; then
  printf 'usage: %s [--anonymous]\n' "$0" >&2
  exit 2
fi

backend=http://127.0.0.1:8787
origin=http://127.0.0.1:8088
credential_file=/etc/training-kb/public-access.json
htpasswd_file=/etc/nginx/training-kb.htpasswd
rate_limit_file=/etc/nginx/conf.d/training-kb-rate-limit.conf
site=/etc/nginx/sites-available/training-kb
enabled=/etc/nginx/sites-enabled/training-kb
runner=/usr/local/sbin/run-training-quick-tunnel
unit=/etc/systemd/system/training-quick-tunnel.service
state_dir=/var/lib/training-tunnel
url_file=$state_dir/public-url.txt
username=kbviewer

curl -fsS --max-time 10 "$backend/api/health" >/dev/null
export DEBIAN_FRONTEND=noninteractive
install -d -o root -g root -m 0755 /usr/share/keyrings
key_tmp=$(mktemp /tmp/cloudflare-main.gpg.XXXXXX)
trap 'rm -f -- "$key_tmp"' EXIT
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o "$key_tmp"
gpg --batch --show-keys "$key_tmp" >/dev/null
install -o root -g root -m 0644 "$key_tmp" /usr/share/keyrings/cloudflare-main.gpg
printf '%s\n' 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' \
  >/etc/apt/sources.list.d/cloudflared.list
apt-get update -qq
apt-get install -y -qq nginx apache2-utils cloudflared ca-certificates >/dev/null

umask 077
password=
if [[ $public_mode == private && -e $credential_file ]]; then
  [[ ! -L $credential_file && -f $credential_file ]] || { printf 'unsafe credential file\n' >&2; exit 1; }
  password=$(python3 - "$credential_file" <<'PY'
import json, pathlib, sys
d=json.loads(pathlib.Path(sys.argv[1]).read_text())
assert d.get('username') == 'kbviewer'
v=d.get('password')
assert isinstance(v,str) and len(v)>=24 and v.isalnum()
print(v)
PY
  )
elif [[ $public_mode == private ]]; then
  password=$(openssl rand -hex 16)
fi
if [[ $public_mode == private ]]; then
  printf '%s\n' "$password" | htpasswd -i -cB "$htpasswd_file" "$username" >/dev/null
  chown root:www-data "$htpasswd_file"
  chmod 0640 "$htpasswd_file"
  auth_block=$'    auth_basic "Private training knowledge base";\n    auth_basic_user_file /etc/nginx/training-kb.htpasswd;'
else
  rm -f -- "$htpasswd_file"
  auth_block='    auth_basic off;'
fi

cat >"$rate_limit_file" <<'EOF'
map $http_cf_connecting_ip $training_kb_client_ip {
    ""      $remote_addr;
    default $http_cf_connecting_ip;
}
limit_req_zone $training_kb_client_ip zone=training_kb_api:10m rate=20r/m;
limit_conn_zone $training_kb_client_ip zone=training_kb_conn:10m;
EOF
chown root:root "$rate_limit_file"
chmod 0644 "$rate_limit_file"

cat >"$site" <<EOF
server {
    listen 127.0.0.1:8088;
    server_name _;
    server_tokens off;
    # training-kb-public-mode: $public_mode

${auth_block}

    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    add_header X-Frame-Options SAMEORIGIN always;

    location ^~ /api/ {
        limit_req zone=training_kb_api burst=10 nodelay;
        limit_req_status 429;
        limit_conn training_kb_conn 4;
        proxy_pass $backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$training_kb_client_ip;
        proxy_set_header X-Forwarded-For \$training_kb_client_ip;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        client_max_body_size 512k;
    }

    location / {
        proxy_pass $backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$training_kb_client_ip;
        proxy_set_header X-Forwarded-For \$training_kb_client_ip;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        client_max_body_size 512k;
    }
}
EOF
ln -sfn "$site" "$enabled"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

id -u training-tunnel >/dev/null 2>&1 || \
  useradd --system --home-dir "$state_dir" --create-home --shell /usr/sbin/nologin training-tunnel
install -d -o training-tunnel -g training-tunnel -m 0700 "$state_dir"

cat >"$runner" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
state=/var/lib/training-tunnel/public-url.txt
tmp=/var/lib/training-tunnel/.public-url.tmp
rm -f -- "$state" "$tmp"
/usr/bin/cloudflared tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:8088 2>&1 |
while IFS= read -r line; do
  printf '%s\n' "$line"
  if [[ $line =~ https://[a-z0-9-]+\.trycloudflare\.com ]]; then
    printf '%s\n' "${BASH_REMATCH[0]}" >"$tmp"
    chmod 0600 "$tmp"
    mv -f -- "$tmp" "$state"
  fi
done
EOF
chown root:root "$runner"
chmod 0755 "$runner"

cat >"$unit" <<'EOF'
[Unit]
Description=Private training portal Cloudflare Quick Tunnel
After=network-online.target nginx.service training-app.service
Wants=network-online.target
Requires=nginx.service training-app.service

[Service]
Type=simple
User=training-tunnel
Group=training-tunnel
ExecStart=/usr/local/sbin/run-training-quick-tunnel
Restart=always
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/training-tunnel
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now training-quick-tunnel.service
for _ in $(seq 1 60); do
  [[ -s $url_file ]] && break
  sleep 2
done
[[ -s $url_file ]] || { journalctl -u training-quick-tunnel.service -n 80 --no-pager >&2; exit 1; }
url=$(cat "$url_file")
[[ $url =~ ^https://[a-z0-9-]+\.trycloudflare\.com$ ]]

# Persist the current URL and access mode without printing any private value.
# The URL can change if the Quick Tunnel restarts.
PUBLIC_URL=$url PUBLIC_MODE=$public_mode PUBLIC_PASSWORD=$password python3 - "$credential_file" <<'PY'
import json, os, pathlib, tempfile, sys
p=pathlib.Path(sys.argv[1])
d={'url':os.environ['PUBLIC_URL']+'/', 'mode':os.environ['PUBLIC_MODE']}
if os.environ['PUBLIC_MODE'] == 'private':
    d.update({'username':'kbviewer', 'password':os.environ['PUBLIC_PASSWORD']})
fd,tmp=tempfile.mkstemp(prefix='.public-access.',dir=str(p.parent))
try:
    os.fchmod(fd,0o600); os.fchown(fd,0,0)
    with os.fdopen(fd,'w',encoding='utf-8') as h:
        json.dump(d,h,ensure_ascii=False,indent=2); h.write('\n'); h.flush(); os.fsync(h.fileno())
    os.replace(tmp,p)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY

code_without_auth=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 60 "$url/")
if [[ $public_mode == anonymous ]]; then
  [[ $code_without_auth == 200 ]]
else
  [[ $code_without_auth == 401 ]]
  code_with_auth=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 60 -u "$username:$password" "$url/")
  [[ $code_with_auth == 200 ]]
fi
unset password PUBLIC_PASSWORD
printf 'quick tunnel enabled: %s/ (mode=%s)\n' "$url" "$public_mode"
