# Host-Level Certbot TLS Setup

This project does not commit certificates or private keys. A simple production approach is to issue and renew certificates on the host, then mount `/etc/letsencrypt` read-only into the nginx container.

## Prerequisites

- Point the DNS `A` record for your production domain, such as `erp.example.com`, to the server public IP.
- Confirm the deployment host firewall allows inbound TCP ports `80` and `443`.
- Confirm `.env.production` has `SERVER_NAME` set to the production hostname, without `http://`, `https://`, or a path.
- Keep certificate and private key files outside the repository.

## Issue Certificates

Install Certbot on the host operating system. For example, on an Ubuntu host:

```sh
sudo apt-get update
sudo apt-get install certbot
```

Stop any process using port `80`, or use a Certbot mode compatible with your host setup. Issue the certificate on the host:

```sh
sudo certbot certonly --standalone -d erp.example.com
```

Confirm the host now has:

```text
/etc/letsencrypt/live/erp.example.com/fullchain.pem
/etc/letsencrypt/live/erp.example.com/privkey.pem
```

Do not copy either file into this repository.

## Enable HTTPS

The default production nginx config remains HTTP-only for local production verification and first boot before certificates exist.

After certificates exist on the host, enable HTTPS with:

```sh
./scripts/enable-production-https.sh .env.production
```

The script:

- validates `.env.production`
- rejects placeholder or local `SERVER_NAME` values
- checks `/etc/letsencrypt/live/$SERVER_NAME/fullchain.pem`
- checks `/etc/letsencrypt/live/$SERVER_NAME/privkey.pem`
- renders `nginx/conf.d/default.prod.https.template.conf` into a generated HTTPS config
- builds nginx with that generated config
- runs `nginx -t`
- recreates or reloads nginx when a running nginx service exists

If LetsEncrypt files are stored somewhere other than `/etc/letsencrypt`, pass the host path with:

```sh
LETSENCRYPT_HOST_PATH=/path/to/letsencrypt ./scripts/enable-production-https.sh .env.production
```

The generated `nginx/conf.d/default.prod.https.conf` file is ignored by Git and should not contain certificate or key contents.

Verify HTTPS:

```sh
curl -I https://erp.example.com/health
curl https://erp.example.com/health/ready
PRODUCTION_STATUS_BASE_URL=https://erp.example.com ./scripts/check-production-status.sh
```

## Renew Certificates

Renew certificates on the host:

```sh
sudo certbot renew
```

Reload nginx after renewal:

```sh
./scripts/reload-production-nginx.sh .env.production
```

Example Certbot deploy hook:

```sh
sudo certbot renew --deploy-hook 'cd /opt/restaurant && ./scripts/reload-production-nginx.sh .env.production'
```

## Notes

- Certificate issuance is still an explicit host-level operator step.
- Do not copy certificates or private keys into the repository.
- HSTS should remain only in the HTTPS server block.
- Keep port `80` open for HTTP-to-HTTPS redirects and future certificate renewal flows.
