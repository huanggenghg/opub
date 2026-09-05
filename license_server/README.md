# opub license service — deployment runbook

`license_server/` is the **private** activation/licensing service for opub. It
never ships to PyPI: `pyproject.toml` does not declare it as a package,
`MANIFEST.in` prunes it (plus `.secrets/` and `*.sqlite3*`) from the source
distribution, and `tests/test_package_build.py` asserts that both the built
wheel and the sdist contain no `license_server/`, `.secrets/`, or `*.sqlite3*`
entries.

Routes (the service exposes exactly three):

| Route | Purpose |
| --- | --- |
| `POST /v1/activation-sessions` | create an activation session, returns checkout URL + poll token |
| `GET /v1/activation-sessions/{session_id}` | poll session status (Bearer poll token required) |
| `POST /v1/webhooks/mianbaoduo` | payment provider webhook |

## 1. Environment variables

All seven are required — the service refuses to start when any is missing or
blank. Write them to `/etc/opub-license.env` (mode `600`, owner
`opub-license:opub-license`):

```bash
OPUB_PUBLIC_BASE_URL=https://license.example.com
OPUB_PAYMENT_RETURN_URL=https://opub.example.com/thanks
OPUB_MBD_APP_ID=<mianbaoduo app id>
OPUB_MBD_APP_KEY=<mianbaoduo app key>
OPUB_LICENSE_PRIVATE_KEY=<base64 32-byte Ed25519 seed from keygen>
OPUB_LICENSE_KEY_ID=<key id, e.g. opub-license-2026-09>
OPUB_LICENSE_DB_PATH=/opt/opub/license_server/data/license.sqlite3
```

Rules enforced at startup (`config.py`):

- Both URLs must be `https`; `OPUB_PUBLIC_BASE_URL` must not carry a query
  string or fragment, and its trailing slash is stripped.
- `OPUB_LICENSE_PRIVATE_KEY` must be valid base64 decoding to exactly 32 bytes.
- `OPUB_MBD_APP_KEY` and `OPUB_LICENSE_PRIVATE_KEY` are secrets: they live only
  in this env file, never in Git and never in a distribution.

For Caddy, additionally set `OPUB_LICENSE_HOST` to the **host portion of
`OPUB_PUBLIC_BASE_URL`** — e.g. `https://license.example.com` →
`OPUB_LICENSE_HOST=license.example.com` — and make it visible to the `caddy`
process (e.g. a systemd drop-in for the caddy unit):

```ini
# /etc/systemd/system/caddy.service.d/opub-license.conf
[Service]
Environment=OPUB_LICENSE_HOST=license.example.com
```

## 2. Key generation

From a trusted machine, in the repo root (this writes the private seed with
mode `600` and the matching public key into a client-side module):

```bash
python -m license_server.keygen \
    --private-file .secrets/license-ed25519-private.b64 \
    --client-file <path-to-client-public-key-module> \
    --base-url https://license.example.com \
    --key-id opub-license-2026-09
```

The base64 line inside the private file is the value for
`OPUB_LICENSE_PRIVATE_KEY`.

**Offline copies:** keep exactly **two offline copies** of the Ed25519 private
key (e.g. one encrypted USB stick and one printed base64 hardcopy in a safe,
or a password-manager entry) in addition to the live env file. The private key
must otherwise exist only in `.secrets/` on the generating machine and in
`/etc/opub-license.env` on the server. Losing all copies means no further
licenses can ever be issued; leaking it means anyone can forge licenses.

## 3. Install and start

```bash
# 1) System user and code checkout
sudo useradd --system --home /opt/opub --shell /usr/sbin/nologin opub-license
sudo git clone <repo> /opt/opub && cd /opt/opub
sudo -u opub-license python -m venv .venv
sudo -u opub-license .venv/bin/python -m pip install -r license_server/requirements.txt
# (with the venv active, the equivalent is:)
python -m pip install -r license_server/requirements.txt

# 2) Environment file (see section 1) and runtime directories
sudo install -o opub-license -g opub-license -m 600 /dev/null /etc/opub-license.env
sudo -u opub-license mkdir -p /opt/opub/license_server/data /var/backups/opub-license

# 3) systemd unit (single worker — see section 5)
sudo cp license_server/deploy/opub-license.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now opub-license
```

The unit runs uvicorn on `127.0.0.1:8013` with
`--proxy-headers --forwarded-allow-ips=127.0.0.1`, so only the local reverse
proxy is trusted to supply the real client IP (the rate limiters key on it).

## 4. Reverse proxy (Caddy)

```bash
sudo cp license_server/deploy/Caddyfile.example /etc/caddy/Caddyfile.d/opub-license
# ensure the main Caddyfile imports the snippet:  import Caddyfile.d/*
sudo systemctl reload caddy   # after setting OPUB_LICENSE_HOST (section 1)
```

`Caddyfile.example` terminates TLS for `{$OPUB_LICENSE_HOST}` and proxies to
`127.0.0.1:8013`.

## 5. Why exactly one worker

Do **not** raise `--workers`. Two pieces of state are process-local:

- The activation-session **creation lock** (`threading.Lock` in
  `service.py`) serializes check-then-insert for pending sessions and order
  creation.
- The **rate limiters** (`limiter.py`) are in-memory sliding windows.

With more than one worker, duplicate checkouts could be created and the rate
limits would only be per-worker. If throughput ever demands scaling, the lock
and limiter must move to shared storage first.

## 6. Smoke test

After start (and after every deploy):

```bash
curl -fsS -o /dev/null -w '%{http_code}\n' "$OPUB_PUBLIC_BASE_URL/v1/activation-sessions/not-found"
```

Expected output: `401`. The polling route exists but requires a Bearer poll
token, and unknown sessions deliberately answer 401 (not 404) to avoid
session enumeration — so 401 proves routing, TLS and the app are all alive.

Note: with `-f`, curl exits non-zero on any 4xx even though `-w` still prints
the status; seeing `401` printed is the expected, healthy result.

## 7. Provider webhook

In the mianbaoduo merchant console, configure the webhook URL as:

```
{OPUB_PUBLIC_BASE_URL}/v1/webhooks/mianbaoduo
```

Use the exact path with **no query parameters** — e.g.
`https://license.example.com/v1/webhooks/mianbaoduo`. The URL carries no
secret; every delivery is re-verified server-side by querying the provider
order API before any license is issued, and repeated deliveries are
idempotent.

## 8. Database backup

Daily backup (cron or systemd timer, run as `root` or `opub-license`):

```bash
sqlite3 "$OPUB_LICENSE_DB_PATH" '.backup /var/backups/opub-license/latest.sqlite3'
```

Keep **30 days** of retention by rotating a dated copy:

```bash
cp -p /var/backups/opub-license/latest.sqlite3 \
      /var/backups/opub-license/license-$(date +%F).sqlite3
find /var/backups/opub-license -name 'license-*.sqlite3' -mtime +30 -delete
```

`.backup` is the safe online-backup command: it holds a read lock only, so the
service can stay up. Never copy the live file with `cp` while the service is
writing.

**Restore drill (before go-live, on a disposable copy — never the live DB):**

```bash
sqlite3 /var/backups/opub-license/latest.sqlite3 'PRAGMA integrity_check;'
cp /var/backups/opub-license/latest.sqlite3 /tmp/restore-drill.sqlite3
OPUB_LICENSE_DB_PATH=/tmp/restore-drill.sqlite3 \
OPUB_PUBLIC_BASE_URL=https://license.example.com \
OPUB_PAYMENT_RETURN_URL=https://opub.example.com/thanks \
OPUB_MBD_APP_ID=... OPUB_MBD_APP_KEY=... \
OPUB_LICENSE_PRIVATE_KEY=... OPUB_LICENSE_KEY_ID=... \
/opt/opub/.venv/bin/uvicorn license_server.app:app_from_env --factory --port 8014
# then poll a known session id from the backup and confirm its status
```

## 9. Release hygiene (client package)

`tests/test_package_build.py` builds the wheel and sdist and asserts the
private service stays out of both. When cutting a release:

```bash
rm -rf build/ dist/ && python -m build
```

Always delete `build/` first: `bdist_wheel` archives the **accumulated**
`build/lib` tree, so files left there by any earlier experimental build would
leak into later wheels (this has been observed with a stale
`build/lib/license_server/`). `.secrets/` is pruned by `MANIFEST.in` and
ignored by Git; the runtime database lives under
`license_server/data/`, which `.gitignore` also excludes.

## 10. Go-live gate

Do not expose the client paywall until all of these are confirmed:

- [ ] The provider has approved the payment scene and both payment methods
      (wechat + alipay).
- [ ] A real HTTPS hostname is in `OPUB_PUBLIC_BASE_URL`.
- [ ] The webhook URL is configured with no query parameters.
- [ ] One internal ¥9.90 order reaches `licensed` exactly once
      (webhook delivery repeated → still exactly one license).
- [ ] SQLite backup restoration has been exercised on a disposable copy
      (section 8).
- [ ] The generated private key exists only in `.secrets/`, the server env
      file, and the two offline backups.
