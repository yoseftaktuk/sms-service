# sms-service

FastAPI service that receives a Nedarim Plus transaction webhook and sends the donation receipt link by SMS (Yemot), then WhatsApp (GreenAPI) if SMS fails.

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

`postgres://` and `postgresql://` URLs are rewritten to `postgresql+asyncpg://` automatically.
