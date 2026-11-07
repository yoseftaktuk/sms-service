# sms-service

FastAPI service that receives a Nedarim Plus transaction webhook and sends the donation receipt link by SMS (Yemot), then WhatsApp (GreenAPI) if SMS fails. When Shlink is configured, the message carries a short URL that redirects to the Ezcount receipt.

Endpoint: `POST /api/v1/webhooks/nedarim/transactions`

## Environment file

Copy the example and fill in the secrets locally. Do not commit `.env`.

```bash
cp .env.example .env
```

### Required

| Variable | What to put |
| --- | --- |
| `DATABASE_URL` | Postgres URL for the app, for example `postgresql+asyncpg://postgres:postgres@localhost:5432/sms_service` |
| `NEDARIM_WEBHOOK_SECRET` | HMAC secret from Nedarim (Webhook settings). The endpoint returns 503 until this is set. |
| `NEDARIM_API_PASSWORD` | Nedarim API password (`npk_...`). Used by `ShowInvoice` when the webhook has no receipt link yet. |
| `YEMOT_API_KEY` | Yemot firewall API key. Sent as the `Authorization` header for `SendSms`. |
| `GREENAPI_ID_INSTANCE` | GreenAPI instance id. Used only when SMS fails. |
| `GREENAPI_API_TOKEN` | GreenAPI API token. Used only when SMS fails. |

### Optional

| Variable | Default | What to put |
| --- | --- | --- |
| `NEDARIM_MOSAD_ID` | `7018669` | Institution id. A webhook with a different `MosadNumber` is rejected. |
| `NEDARIM_HMAC_MAX_SKEW_SECONDS` | `300` | How far `X-Nedarim-Timestamp` may be from the current time. |
| `YEMOT_SMS_FROM` | empty | Approved sender id. Leave empty to use Yemot's default. |
| `YEMOT_API_BASE_URL` | `https://www.call2all.co.il/ym/api` | Yemot API base URL. |
| `GREENAPI_API_URL` | `https://api.green-api.com` | GreenAPI base URL. |
| `ENVIRONMENT` | `development` | `development` or `production`. |
| `TEST_DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/sms_service_test` | Postgres URL used only by pytest. |
| `SHLINK_BASE_URL` | empty | Shlink origin reachable from this service, for example `https://s.example.com` or an internal URL. Empty skips shortening and sends the Ezcount URL. |
| `SHLINK_API_KEY` | empty | Shlink API key. The same value as `INITIAL_API_KEY` on the first Shlink boot. Empty skips shortening. |

`postgres://` and `postgresql://` URLs are rewritten to `postgresql+asyncpg://` automatically.

## Short links

Shlink runs as its own container (`shlinkio/shlink:stable`). It is not part of this process. It answers `GET /{code}` with a redirect to the Ezcount receipt. This service only calls `POST /rest/v3/short-urls`.

The website keeps the apex domain and `www`. Add one DNS record, `s.example.com`, as an A or CNAME to the Shlink host. Do not set website cookies with `Domain=.example.com`, or browsers will send them to the short domain.

Shlink listens on port 8080 over HTTP. Put a TLS reverse proxy in front of it for `s.example.com` only, forwarding to `127.0.0.1:8080`. Set `DEFAULT_DOMAIN=s.example.com` and `IS_HTTPS_ENABLED=true` so the SMS link is `https://s.example.com/{code}`.

Persist the SQLite database on a private volume mounted at `/etc/shlink/data`. That file holds every receipt URL. Do not publish the volume or its backups.

```bash
docker run --name shlink \
  -p 127.0.0.1:8080:8080 \
  -v shlink-data:/etc/shlink/data \
  -e DEFAULT_DOMAIN=s.example.com \
  -e IS_HTTPS_ENABLED=true \
  -e INITIAL_API_KEY='replace-with-a-long-random-value' \
  -e AUTO_RESOLVE_TITLES=false \
  -e DISABLE_TRACKING=true \
  -e DEFAULT_SHORT_CODES_LENGTH=10 \
  -e SHORT_URL_MODE=strict \
  shlinkio/shlink:stable
```

`INITIAL_API_KEY` is stored as a hash. Copy it into `SHLINK_API_KEY` before you remove it. After the first successful boot, delete `INITIAL_API_KEY` from the container environment and start the container again. The hashed key in the volume stays valid. If the image refuses to start without `GEOLITE_LICENSE_KEY`, set a free MaxMind key. Tracking is disabled, so visits are not stored.

`SHLINK_BASE_URL` is the origin this service can call. Use `https://s.example.com` when the API is public, or an internal URL when it is not. The link placed in the SMS is the `shortUrl` field from Shlink, built from `DEFAULT_DOMAIN`, not from `SHLINK_BASE_URL`.

On the proxy, rate-limit requests for unknown codes. Leave `GET /{code}` and `GET /rest/health` public. Block the rest of `/rest` from the internet when sms-service can reach Shlink on a private network. Define the limit zone in the proxy's `http` block, not inside the server:

```nginx
limit_req_zone $binary_remote_addr zone=shlink:10m rate=10r/s;

server {
    listen 443 ssl;
    server_name s.example.com;

    location = /rest/health {
        proxy_pass http://127.0.0.1:8080;
    }

    location /rest/ {
        allow 10.0.0.0/8;
        deny all;
        proxy_pass http://127.0.0.1:8080;
    }

    location / {
        limit_req zone=shlink burst=20 nodelay;
        proxy_pass http://127.0.0.1:8080;
    }
}
```

If sms-service must call the public origin, drop the `allow`/`deny` lines and rely on a long random API key.

Only `https://files.ezcount.co.il/...` receipts are shortened. Any other URL is sent unchanged. A failed Shlink call also sends the original Ezcount URL, and the donation is still delivered.

Check the instance with `GET https://s.example.com/rest/health`. The body is JSON with `"status": "pass"`. Then shorten one receipt and open the short link. It should redirect to the Ezcount document.
