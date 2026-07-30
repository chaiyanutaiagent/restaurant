# Production Uploads

Uploaded files are stored in the backend container at `/app/uploads`. In production, `docker-compose.prod.yml` mounts the `uploads` named volume at that path so files survive backend container rebuilds and restarts.

## Allowed Files

The production defaults are image-only:

- Extensions: `.jpg`, `.jpeg`, `.png`, `.webp`
- MIME types: `image/jpeg`, `image/png`, `image/webp`
- Maximum size: `5 MB`

The backend validates the declared MIME type and the detected file content type. Dangerous extensions such as executable, shell, PHP, JavaScript, and HTML files are rejected.

## Filename Safety

The backend rejects path traversal filenames, does not use user-provided filenames for storage, and writes files using UUID-based names. The final resolved path must remain inside the configured upload directory.

## Serving Uploads

The backend serves `/uploads/` from the upload directory. Production nginx proxies `/uploads/` to the backend, keeps `X-Content-Type-Options: nosniff`, disables directory listing, and limits request body size to match the backend default.

## Configuration

Production upload settings live in `.env.production`:

```sh
UPLOAD_DIR=/app/uploads
MAX_UPLOAD_SIZE_MB=5
ALLOWED_UPLOAD_EXTENSIONS=[".jpg",".jpeg",".png",".webp"]
ALLOWED_UPLOAD_MIME_TYPES=["image/jpeg","image/png","image/webp"]
```

Keep these values restrictive unless there is a reviewed product requirement for additional file types.

## Backup and Restore

Uploads are included in the PR8 backup workflow as `uploads.tar.gz`. Restore replaces the target upload volume contents, so verify the restore target and run restore drills with an isolated `COMPOSE_PROJECT_NAME` before using production backups.

See [backup-restore.md](./backup-restore.md) for backup and restore commands.

## Manual Verification

After deploying a production stack:

```sh
curl http://localhost/health/ready
docker compose -f docker-compose.prod.yml exec -T nginx nginx -t
docker compose -f docker-compose.prod.yml exec -T backend sh -c 'test -w /app/uploads'
```

Use the authenticated product image upload API to verify:

- A valid JPEG, PNG, or WebP image succeeds.
- A dangerous extension such as `.sh`, `.php`, `.js`, or `.html` is rejected.
- A path traversal filename such as `../image.jpg` is rejected.
- A file larger than `MAX_UPLOAD_SIZE_MB` is rejected.

Do not store malware samples or real customer files in the repository while testing.

## Known Limitations

- Uploaded files are public to anyone who can request their `/uploads/...` URL.
- Antivirus or malware scanning is not implemented yet.
- Object storage is not configured yet.
- Per-tenant upload quotas and lifecycle cleanup are not implemented yet.
