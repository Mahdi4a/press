# Setting up Press servers in Iran

Runbook for bringing up a Proxy Server and an App Server (with its
database) on Ubuntu 22.04 VMs that cannot reach the public internet
freely. It records every manual step we needed, so the next server does
not have to be debugged again.

Layout:

| Server | Role | Example |
|---|---|---|
| Press | dashboard, runs Ansible and Agent Jobs | `press.ezrun.ir` |
| Proxy | `*.sites.<domain>`, TLS, forwards to the App Server | `n1.sites.ezrun.ir` |
| App + DB | benches, MariaDB | `agent.sites.ezrun.ir`, `db.sites.ezrun.ir` |

Use Ubuntu 22.04 for every managed server. 24.04 needed several extra
fixes and is not supported by these playbooks.

## 1. Before you start

Collect:

- the public IP of the VM and a sudo user that can log in;
- the wildcard TLS Certificate for `sites.<domain>` in Press;
- the PyPI mirror, `https://repo.dev.pol-crm.ir/repository/pypi-proxy/simple/`.

DNS (Cloudflare, "DNS only"):

| Name | Content |
|---|---|
| `n1.sites` | proxy IP |
| `agent.sites` | app server IP |
| `db.sites` | app server IP |
| `*.sites` | proxy IP (switch last, after the proxy answers) |

A specific record always wins over the wildcard, so create `agent.sites`
and `db.sites` **before** pointing `*.sites` at the proxy.

## 2. Prepare every new VM

1. Free UID 1000. The `user` role creates `frappe` with UID 1000. If the
   VM's first user has it, Ansible fails at `Create Frappe User`.

   ```bash
   getent passwd | awk -F: '$3>=1000 && $3<65000 {print $1, $3}'
   pkill -u NAME; usermod -u 1100 NAME && groupmod -g 1100 NAME
   find /home/NAME -xdev -user 1000 -exec chown -h NAME:NAME {} +
   ```

2. Let Press log in as `root` with its key. Take the public key from the
   Press host (`/home/eftekhari/press/ssh/id_ed25519.pub`):

   ```bash
   install -d -m 700 /root/.ssh
   echo "<public key>" >> /root/.ssh/authorized_keys
   chmod 600 /root/.ssh/authorized_keys
   ```

   Check from the Press host:

   ```bash
   docker exec <queue-long> ssh -i /home/frappe/.ssh/id_ed25519 \
     -o StrictHostKeyChecking=accept-new root@<ip> hostname
   ```

3. Make sure the VM resolves the PyPI mirror and ports 80/443 are free
   (`ss -ltnp | grep -E ':(80|443) '`).

## 3. Press-side setup

All of this is in the Desk, `https://<press>/desk/press/...`, not in the
dashboard.

1. Create the **Proxy Server** (`/desk/press/proxy-server/new`):
   Hostname `n1`, Domain `sites.<domain>`, IP and Private IP set to the
   proxy IP, Cluster, Status `Pending`.
2. Actions, **Setup Server**.
3. When the play ends, the status may show **Broken** even if Ansible
   reported `failed=0`. This is the callback issue with ansible-core 2.19.
   Check the real result:

   ```bash
   docker logs --tail 400 <queue-long> 2>&1 \
     | grep -E "^TASK \[|^fatal|PLAY RECAP|failed=" | cut -c1-400 | tail -n 8
   ```

   With `failed=0`, set the status by hand:

   ```bash
   bench --site <press-site> execute frappe.db.set_value \
     --args '["Proxy Server","n1.sites.<domain>",{"status":"Active","is_server_setup":1}]'
   ```

4. On the **Server** record set `proxy_server`, clear `is_standalone`,
   and set `private_ip` to the IP the proxy can reach (the public IP when
   there is no private network). The proxy writes this IP into its
   upstream files. The **Database Server** keeps its own `private_ip`
   (`172.17.0.1`), so the bench still reaches MariaDB on the Docker
   bridge.

## 4. Known failures during Setup Server

| Symptom | Cause | Fix |
|---|---|---|
| `usermod`/`useradd` UID 1000 exists | the VM's first user has UID 1000 | step 2.1 |
| `Failed to download key ... artifacts.elastic.co 403` | Filebeat repository blocked | `filebeat` is commented out in `playbooks/server.yml` and `playbooks/proxy.yml` |
| `pip install` of the agent: `Temporary failure in name resolution` | `files.pythonhosted.org` is unreachable | write `/home/frappe/.config/pip/pip.conf` with the mirror (below) |
| the same step: `HTTP error 404 ... Failed to resolve host: files.pythonhosted.org` | the mirror could not reach upstream and cached the 404 | fix DNS on the mirror and use **Invalidate cache**; or install the agent offline (below) |
| `sshd` service not found | Ubuntu names it `ssh` | already fixed in the roles |
| `apt` panic in Ansible | ansible-core 2.21 | pinned to 2.19.14 in the Press image |

`pip.conf` for the `frappe` user:

```ini
[global]
index-url = https://repo.dev.pol-crm.ir/repository/pypi-proxy/simple/
timeout = 120
```

Offline install of the agent, when the mirror misses a package. On a
machine with internet, from a Python 3.10 container:

```bash
git clone --depth 1 https://github.com/frappe/agent
docker run --rm -v "$PWD/wheels:/w" -v "$PWD/agent/requirements.txt:/r.txt:ro" \
  python:3.10-slim pip download -r /r.txt -d /w
tar -czf agent-wheels.tgz -C wheels .
```

Copy the archive to the VM, then:

```bash
mkdir /tmp/agent-wheels && tar -xzf /tmp/agent-wheels.tgz -C /tmp/agent-wheels
chmod -R a+rX /tmp/agent-wheels
sudo -u frappe /home/frappe/agent/env/bin/pip3 install --no-index \
  --find-links /tmp/agent-wheels -e file:///home/frappe/agent/repo
```

Set the status back to `Pending` and run **Setup Server** again. The play
is idempotent and skips what is already done.

## 5. App server notes

- MariaDB listens on the Docker bridge only (`bind-address = 172.17.0.1`),
  and starts after Docker (`/etc/systemd/system/mariadb.service.d/after-docker.conf`).
  Press needs `root` grants for `172.17.%`, `172.17.0.1` and the public IP.
- A **Database Server** record must exist and be linked from the Server.
  It is where Press reads the root password.
- The Server needs a `team`, or the version list in the dashboard is empty.
- Check that nginx can read the bench files. nginx runs as `www-data`,
  and `/home/frappe` is mode 750, so `www-data` must be in the `frappe`
  group. The `nginx` role adds it during Setup, but a `frappe` user that was
  created by hand skips that step. Without it the page loads, but every
  `/assets/...` request returns 404 and `error.log` shows
  `Permission denied (13)`:

  ```bash
  id www-data                       # must list frappe
  usermod -aG frappe www-data && systemctl reload nginx
  ```

- Allow only the proxy to reach port 80. Frappe Cloud does this with a
  cloud security group, which a plain VM does not have. Use a separate
  nftables table, loaded by its own unit. Do **not** use `iptables-persistent`
  or `iptables -A` on a host that runs Docker: saving and restoring the
  rules wipes Docker's NAT chains, the published ports (`127.0.0.1:18001`)
  stop answering, and nginx hangs on every request:

  ```bash
  cat > /etc/ezrun-firewall.nft <<'EOF'
  table inet ezrun_fw {
    chain input {
      type filter hook input priority -10; policy accept;
      tcp dport 80 ip saddr { <proxy ip>, 127.0.0.1, 172.16.0.0/12 } accept
      tcp dport 80 drop
    }
  }
  EOF
  cat > /etc/systemd/system/ezrun-firewall.service <<'EOF'
  [Unit]
  Description=Allow port 80 only from the proxy
  After=network.target

  [Service]
  Type=oneshot
  RemainAfterExit=yes
  ExecStartPre=-/usr/sbin/nft delete table inet ezrun_fw
  ExecStart=/usr/sbin/nft -f /etc/ezrun-firewall.nft
  ExecStop=/usr/sbin/nft delete table inet ezrun_fw

  [Install]
  WantedBy=multi-user.target
  EOF
  systemctl daemon-reload && systemctl enable --now ezrun-firewall
  ```

  Keep 443 open. Press calls the agent on it. If the Docker NAT chains were
  wiped by mistake, `systemctl restart docker` rebuilds them (check with
  `nft list chain ip nat DOCKER`), then start the bench containers.
- The agent's `config.json` on the app server must not contain
  `standalone` or `domain`, and `proxy_ip` must be the proxy IP, so
  `set_real_ip_from` trusts only the proxy.
- After leaving standalone mode, regenerate each bench's nginx file. In
  standalone mode the bench listens on 443 and redirects 80 to https, which
  loops behind the proxy:

  ```python
  # sudo -u frappe sh -c 'cd /home/frappe/agent && env/bin/python regen.py'
  from agent.server import Server
  s = Server()
  for name, bench in s.benches.items():
      bench.generate_nginx_config()
  s._reload_nginx()
  ```

## 6. Moving an existing site behind the proxy

```python
# bench --site <press-site> console
from press.agent import Agent
a = Agent("n1.sites.<domain>", server_type="Proxy Server")
a.new_upstream_file(server="agent.sites.<domain>", site="<site>")
frappe.db.commit()
```

Check before touching DNS:

```bash
curl -skI --resolve <site>:443:<proxy ip> https://<site>/ | grep -iE "^HTTP|^x-proxy"
```

Expect `HTTP/2 200` and an `x-proxy-upstream` header. New sites created by
Press get this file automatically.

Then load a CSS file from the same URL. A `404` on `/assets/...` while the
page itself loads is a permission problem (section 5), not a stale cache:

```bash
curl -s https://<site>/login | grep -oE '/assets/[^"]+\.css' | head -n 1 \
  | xargs -I{} curl -sI https://<site>{} | head -n 3
```

## 7. Hardening after setup

- `chmod 600 /home/frappe/agent/tls/privkey.pem` on the proxy.
- Turn off password logins once key login works:

  ```bash
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sshd -t && systemctl reload ssh
  ```

  The proxy receives password guesses for `root` within minutes of coming
  online.
- Do not expose Redis. A cache started with `docker run -p 0.0.0.0:...`
  is open to everyone.

## 8. Changes that live only in the Press image

These are in the `feat/zarinpal-signalads-sms` branch and reach the
running containers through the GitLab pipeline:

- `playbooks/server.yml` and `playbooks/proxy.yml` skip Filebeat;
- `playbooks/roles/*`: `sshd` renamed to `ssh`, NAT checks use booleans;
- `docker/Dockerfile`: PyPI mirror and Playwright CDN for Chromium.

Until a pipeline has run, the Filebeat change can be applied to the
running containers with:

```bash
for c in $(docker ps --format '{{.Names}}' | grep -E 'queue|worker|backend|scheduler'); do
  docker exec "$c" sed -i 's/^    - role: filebeat$/    # - role: filebeat/' \
    /home/frappe/frappe-bench/apps/press/press/playbooks/proxy.yml
done
```
