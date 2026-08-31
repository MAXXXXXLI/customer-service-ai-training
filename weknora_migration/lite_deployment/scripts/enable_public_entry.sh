#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  printf 'run as root\n' >&2
  exit 1
fi
if [[ $# -ne 1 ]]; then
  printf 'usage: %s <public-domain>\n' "$0" >&2
  exit 2
fi

domain=$1
[[ $domain =~ ^[A-Za-z0-9.-]+$ ]] || { printf 'invalid domain\n' >&2; exit 2; }
backend=http://127.0.0.1:8787
credential_file=/etc/training-kb/public-access.json
htpasswd_file=/etc/nginx/training-kb.htpasswd
site=/etc/nginx/sites-available/training-kb
enabled=/etc/nginx/sites-enabled/training-kb
webroot=/var/www/certbot
username=kbviewer

curl -fsS --max-time 10 "$backend/api/health" >/dev/null
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx apache2-utils certbot ca-certificates >/dev/null

umask 077
install -d -o root -g root -m 0755 "$webroot/.well-known/acme-challenge"
if [[ -e $credential_file ]]; then
  [[ ! -L $credential_file && -f $credential_file ]] || { printf 'unsafe credential file\n' >&2; exit 1; }
  password=$(python3 - "$credential_file" "$domain" <<'PY'
import json, pathlib, sys
p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text())
assert d.get('url') == 'https://' + sys.argv[2] + '/'
assert d.get('username') == 'kbviewer'
v=d.get('password')
assert isinstance(v,str) and len(v)>=24 and v.isalnum()
print(v)
PY
  )
else
  password=$(openssl rand -hex 16)
  PUBLIC_PASSWORD=$password python3 - "$credential_file" "$domain" <<'PY'
import json, os, pathlib, sys, tempfile
p=pathlib.Path(sys.argv[1]); p.parent.mkdir(parents=True,exist_ok=True)
d={'url':'https://'+sys.argv[2]+'/', 'username':'kbviewer', 'password':os.environ['PUBLIC_PASSWORD']}
fd,tmp=tempfile.mkstemp(prefix='.public-access.',dir=str(p.parent))
try:
    os.fchmod(fd,0o600); os.fchown(fd,0,0)
    with os.fdopen(fd,'w',encoding='utf-8') as h:
        json.dump(d,h,ensure_ascii=False,indent=2); h.write('\n'); h.flush(); os.fsync(h.fileno())
    os.replace(tmp,p)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
PY
fi
printf '%s\n' "$password" | htpasswd -i -cB "$htpasswd_file" "$username" >/dev/null
chown root:www-data "$htpasswd_file"
chmod 0640 "$htpasswd_file"

# Keep the application unavailable while ACME is being bootstrapped.
cat >"$site" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $domain;
    location ^~ /.well-known/acme-challenge/ { root $webroot; }
    location / { return 503; }
}
EOF
ln -sfn "$site" "$enabled"
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx

if [[ ! -s /etc/letsencrypt/live/$domain/fullchain.pem ]]; then
  certbot certonly --webroot -w "$webroot" -d "$domain" \
    --non-interactive --agree-tos --register-unsafely-without-email
fi

cat >"$site" <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $domain;
    location ^~ /.well-known/acme-challenge/ { root $webroot; }
    location / { return 301 https://\$host\$request_uri; }
}

server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name $domain;
    server_tokens off;

    ssl_certificate /etc/letsencrypt/live/$domain/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$domain/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:TLS:10m;
    ssl_session_timeout 1d;

    add_header Strict-Transport-Security "max-age=2592000" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy same-origin always;
    add_header X-Frame-Options SAMEORIGIN always;

    auth_basic "Private training knowledge base";
    auth_basic_user_file $htpasswd_file;

    location / {
        proxy_pass $backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_buffering off;
        proxy_request_buffering off;
        proxy_read_timeout 600s;
        proxy_send_timeout 600s;
        client_max_body_size 16m;
    }
}
EOF

install -d -o root -g root -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/reload-nginx <<'EOF'
#!/usr/bin/env sh
set -eu
nginx -t
systemctl reload nginx
EOF
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx

nginx -t
systemctl reload nginx

code_without_auth=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "https://$domain/")
[[ $code_without_auth == 401 ]]
code_with_auth=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -u "$username:$password" "https://$domain/")
[[ $code_with_auth == 200 ]]
unset password PUBLIC_PASSWORD
printf 'public entry enabled: https://%s/ (credentials stored root-only; password not printed)\n' "$domain"
