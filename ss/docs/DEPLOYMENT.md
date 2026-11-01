# Ubuntu VPS deployment — step by step

**Target:** Hostinger KVM 2, Ubuntu, no GPU. **This document deploys the revised v1.1 package.** These commands operate on YOUR VPS, not inside ChatGPT. Check whether you already have services on ports 80/443 before deploying. Never paste passwords or private keys into chat.

## 0. Before anything: collect basic server details (read-only)

SSH to your Ubuntu server using Hostinger's console or terminal:

```bash
cat /etc/os-release
uname -m
free -h
df -h /
sudo ss -ltnp | grep -E ':80 |:443 |:8000 ' || true
docker --version || true
docker compose version || true
```

Confirm `x86_64` architecture, 8 GB (approximately) RAM, and enough free storage. If 80/443 are occupied, **stop here**: either configure your existing reverse proxy to forward to the app or adapt the compose file; do not stop other applications blindly. Docker's published ports can bypass some firewall expectations; only the proxy should publish ports to the internet.

## 1. Install Docker (if not already installed)

Follow the current official Ubuntu instructions: https://docs.docker.com/engine/install/ubuntu/ . Prefer Docker's official apt repository and the `docker-compose-plugin`. Do not run arbitrary internet shell scripts as root. Recheck `docker compose version` afterward. Use `sudo docker ...` rather than adding yourself to the docker group if you want to avoid granting your login user root-equivalent Docker permissions.

## 2. Create a PRIVATE GitHub repository

On GitHub, create a private empty repo (e.g. `surprise-signs-digitizer`). On your personal computer, unzip the delivered project folder and commit it. Do NOT commit the `data` folder, the `.env` file, or customer photographs.

On your computer, in the unzipped project directory:

```bash
git init
git add .
git commit -m "Initial Surprise Signs digitizer"
git branch -M main
git remote add origin git@github.com:YOUR-ACCOUNT/surprise-signs-digitizer.git
git push -u origin main
```

Set up GitHub SSH authentication for your computer using GitHub's docs if needed: https://docs.github.com/en/authentication/connecting-to-github-with-ssh . You can also upload the project using GitHub's web interface, but keep it private.

## 3. Connect Ubuntu to your GitHub repository

On the **VPS**, generate a *read-only deploy key* (never reveal the private key):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/surprise_signs_deploy -C "surprise-signs-vps" -N ''
cat ~/.ssh/surprise_signs_deploy.pub
```

Copy ONLY the `.pub` output into GitHub → repository → Settings → Deploy keys → Add deploy key. Leave write access disabled.

On the VPS, register the key in your SSH configuration:

```bash
cat >> ~/.ssh/config <<'CONFIG'
Host github-surprise
    HostName github.com
    User git
    IdentityFile ~/.ssh/surprise_signs_deploy
    IdentitiesOnly yes
CONFIG
chmod 600 ~/.ssh/config
ssh -T git@github-surprise
```

Verify GitHub's SSH host fingerprint using GitHub's published fingerprints before accepting it: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/githubs-ssh-key-fingerprints .

Then clone (replace `YOUR-ACCOUNT`):

```bash
mkdir -p ~/apps
cd ~/apps
git clone git@github-surprise:YOUR-ACCOUNT/surprise-signs-digitizer.git
cd surprise-signs-digitizer
```

## 4. Configure private data folder and environment

```bash
mkdir -p data
sudo chown -R 10001:10001 data
chmod 700 data
cp .env.example .env
chmod 600 .env
nano .env
```

Set `SITE_ADDRESS` and `ALLOWED_HOSTS` to your actual domain. Keep `COOKIE_SECURE=true`. Set a DNS A record to your VPS public IPv4 address. Caddy uses ports 80/443 to issue HTTPS certificates. Do not use a sample `example.com` hostname in production. If you do not have a domain, ask for a VPN-only or private-access variant before deploying; do not expose HTTP login to the open internet.

## 5. Build and launch

```bash
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail=100 api
sudo docker compose logs --tail=100 worker
sudo docker compose logs --tail=100 caddy
```

The worker container is large because it includes PaddlePaddle/PaddleOCR. On a CPU-only 8 GB machine, it may take time to build and the first OCR job may download recognition models. Model caching is stored under the data volume. The server should have ample disk capacity during build.

## 6. Create your administrator account

```bash
sudo docker compose exec -it api python -m app.cli create-admin admin
```

Type a strong password twice at the prompts. Do not store it in `.env`, GitHub, or command history. Visit `https://YOUR-DOMAIN`, log in, upload ONE reference photo via **Form template**, adjust the 13 regions, and click **Save calibrated regions**. The app deliberately blocks batch uploads until calibration is saved. Click **Test photo alignment** with another representative image, then upload a pilot batch. Misaligned photos fail safely and can be entered manually or retried. Verify OCR values before bulk uploads.

## 7. Smoke test and monitor

```bash
sudo docker compose ps
sudo docker compose logs -f worker
```

Check dashboard status, inspect a completed order, correct fields, and export `.xlsx`. If jobs show failed, inspect the worker logs. **No real PaddleOCR accuracy was measured during ChatGPT development; run your own 30–50 photo benchmark before bulk processing.**

## 8. Optional: disable outbound network access for the OCR worker

The worker requires internet on initial model download. Once it has successfully processed a pilot image, you can optionally disable its network access with the provided Compose override:

```bash
sudo docker compose -f docker-compose.yml -f docker-compose.offline.yml up -d --no-build
sudo docker compose -f docker-compose.yml -f docker-compose.offline.yml logs --tail=100 worker
```

Check that a **new** test order still processes successfully. If the model tries to download additional files after network isolation, revert to the normal `sudo docker compose up -d` and resolve local caching before claiming offline readiness. Caddy still requires normal networking for HTTPS certificates. The application contains no hosted OCR API calls.

## 9. Evaluate handwriting accuracy

See [`OCR_EVALUATION.md`](OCR_EVALUATION.md) for how to create a private ground-truth CSV and print aggregate OCR accuracy statistics. The new spreadsheet contains `Orders`, `Original OCR` and `Review queue` worksheets.

## 10. Updates

```bash
cd ~/apps/surprise-signs-digitizer
git pull --ff-only
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
```

Always perform a backup first. Review code changes before pulling; do not set up blind automatic updates until a successful initial deployment.

## 11. Backup and restore

Stop the worker before making a filesystem backup so no jobs are running. SQLite's live WAL files require a consistent snapshot; the safest basic option is stopping the application briefly:

```bash
sudo docker compose stop worker api
sudo tar -czf "$HOME/surprise-signs-backup-$(date +%Y%m%d).tar.gz" data/
sudo docker compose up -d
```

Store the archive securely outside the VPS (encrypted backup storage). It contains personal customer information and local model weights. To restore, stop containers, restore `data/` into the same project directory with UID 10001 ownership, and start Compose again. Test restoration on a separate server before relying on backups.

## Troubleshooting

- **Bad gateway:** run `docker compose ps` and read API logs; verify the API health check.
- **OCR fails on first job:** inspect worker logs and available memory/disk. PaddleOCR model downloads require network during initialization.
- **Model download or dependency conflict:** compare with current official installation instructions: https://www.paddleocr.ai/main/en/quick_start.html . The integration has not yet been validated against this exact Hostinger hardware.
- **Wrong handwritten fields:** update Form template regions and upload a fresh test photo. Already-uploaded forms keep the template version assigned at upload.
- **No certificates:** check DNS and reachable TCP ports 80/443. Caddy needs a real accessible hostname for normal automatic HTTPS.
- **Other web service on ports 80/443:** do not disable it automatically. Integrate with that existing proxy instead.
- **Browser says login failed after success:** ensure the site uses HTTPS when `COOKIE_SECURE=true`, and that `ALLOWED_HOSTS` matches the domain.

## Known deployment limits

The application supports one narrow, tested additive migration: existing v1 templates gain a `calibrated` flag initialized to false. **Back up the database before upgrading.** Full Alembic migrations for future schema changes are not yet implemented. Existing installations must re-save template calibration to enable new uploads. See `IMPLEMENTATION_STATUS.md` for outstanding production-hardening items.
