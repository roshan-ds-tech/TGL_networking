# Deploying the backend to Oracle Cloud "Always Free"

A real VPS with a persistent disk, free forever (not a trial). More setup
than a one-click PaaS, but you own the box and nothing gets wiped on restart.

Total cost: **$0/month**, forever, as long as you stay within the Always
Free shapes below.

## 1. Create the account

1. Sign up at [cloud.oracle.com](https://www.oracle.com/cloud/free/). A card
   is required for identity verification but the Always Free resources are
   never billed.
2. Oracle's free-tier VM capacity (especially the ARM shape below) is
   sometimes unavailable in a given region at signup time — if VM creation
   fails with "out of capacity", retry in a few hours or try a different
   Availability Domain within your region.

## 2. Create the VM

**Compute → Instances → Create instance.**

- **Image:** Ubuntu 22.04 (or 24.04)
- **Shape:** click "Change shape" →
  - `VM.Standard.A1.Flex` (Ampere ARM) — up to **4 OCPU / 24 GB RAM** free,
    the better option if available in your region, **or**
  - `VM.Standard.E2.1.Micro` (AMD) — 1 OCPU / 1 GB RAM, always available,
    plenty for this app's traffic (a few hundred registrations)
- **Add SSH key:** let Oracle generate one, or paste your own public key.
  Download the private key — you cannot retrieve it later.
- Leave networking on the default VCN. Create.

Note the instance's **public IP address** once it's running.

## 3. Open the firewall — two layers, both required

Oracle VMs are blocked by default at two independent layers. Missing either
one means "it works over SSH but the site never loads."

**a) Cloud-level (Security List):**
Networking → Virtual Cloud Networks → your VCN → Security Lists → the
default list → **Add Ingress Rules**, twice:

| Source CIDR | Protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | 80 |
| `0.0.0.0/0` | TCP | 443 |

**b) OS-level (iptables on the VM itself):**
Handled automatically by `deploy/setup-oracle-vm.sh` in step 5 below.

## 4. Point a free domain at the VM

Let's Encrypt (which Caddy uses for automatic HTTPS) cannot issue a
certificate for a bare IP address — you need a real hostname. If you don't
already have a domain:

1. Go to [duckdns.org](https://www.duckdns.org), sign in (GitHub/Google),
   create a subdomain, e.g. `tgl-admin` → `tgl-admin.duckdns.org`.
2. Point it at your VM's public IP (DuckDNS's dashboard has an IP field —
   paste the address from step 2).

If your client wants their own domain later, just repoint its DNS `A` record
at the same IP and update `DOMAIN` in the root `.env` — no other changes.

## 5. Deploy

From your own machine, copy the repo up and SSH in:

```bash
ssh ubuntu@<VM_IP>
```

Then, on the VM:

```bash
git clone https://github.com/roshan-ds-tech/TGL.git ~/TGL
cd ~/TGL
bash deploy/setup-oracle-vm.sh
```

The script installs Docker, opens the OS firewall for 80/443, and creates
`backend/.env` and `.env` from templates. It will stop and tell you to edit
`backend/.env` — fill in:

```bash
nano backend/.env
```

```
SECRET_KEY=<paste output of: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
PUBLIC_ORIGIN=https://tglwebsite.vercel.app
```

Then bring it up:

```bash
docker compose up -d --build
docker compose exec api python create_admin.py
```

Visit `https://tgl-admin.duckdns.org/admin` (using the domain from step 4).
Caddy provisions the TLS certificate automatically on first request — the
very first load may take a few seconds longer while that happens.

## Updating after code changes

```bash
ssh ubuntu@<VM_IP>
cd ~/TGL && git pull
docker compose up -d --build
```

The database and uploaded screenshots live in `~/TGL/data/` on the
host (bind-mounted into the container), so rebuilding never touches them.

## Backups

Oracle's free tier does not snapshot your disk automatically. Periodically
copy `~/TGL/data/` (contains `tgl.db` and `uploads/`) somewhere else —
e.g.:

```bash
scp -r ubuntu@<VM_IP>:~/TGL/data ./tgl-backup-$(date +%F)
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| SSH works, site doesn't load | Security List rule missing (step 3a) |
| `curl` from the VM itself works, browser doesn't | Security List rule missing (step 3a) |
| Everything times out, even SSH | OS firewall — re-run the iptables lines in `setup-oracle-vm.sh` |
| Caddy logs "certificate error" | DNS hasn't propagated yet, or `DOMAIN` in `.env` is wrong — `dig +short your-domain` should show the VM's IP |
| Login works locally but not after deploy | Cookies need HTTPS in production — confirm you're on `https://`, not `http://` |
