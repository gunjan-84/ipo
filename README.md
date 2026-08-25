# Kite IPO Dashboard

A frontend for Zerodha Kite's IPO APIs (multi-account login → view/apply/cancel IPOs), built from `IPO.postman_collection.json`.

Kite's APIs are cookie/CORS-restricted to their own origin, so a small Express backend proxies requests and holds each account's `enctoken` server-side — the browser never talks to Kite directly.

Instead of a manual login + TOTP screen, you save each Zerodha account's `user_id`, password, and TOTP secret (the Base32 secret from your authenticator app setup, not a 6-digit code) once. The backend derives the current TOTP code itself (same HMAC-SHA1 algorithm as the Postman collection's pre-request script) and logs in on demand — so you can hold multiple accounts and connect/switch between them with one click.

## Structure

- `server/` — Express backend.
  - `POST /api/accounts` — save an account (`label`, `user_id`, `password`, `totp_secret`). Credentials are encrypted at rest (`server/data/accounts.json`, AES-256-GCM) and never returned by the API.
  - `POST /api/accounts/:id/connect` — logs in with the stored credentials, computes the TOTP, and caches the resulting `enctoken` in **Redis** (`conn:<accountId>`, ~20h TTL matching Kite's daily token expiry) against that account. Unlike an in-memory store, this survives the server container restarting.
  - Any call to Kite that comes back with `Incorrect \`api_key\` or \`access_token\`.` auto-deletes that account's Redis entry — an expired/invalid enctoken drops the account back to "not connected" instead of silently failing forever.
  - `GET/POST/DELETE /api/accounts/:id/ipo/...` — proxies instruments/applications/apply/cancel to `kite.zerodha.com` using the connected account's `enctoken`.
- `client/` — React (Vite) frontend. Accounts page (add/connect/switch) → IPO list (apply) / My Applications (cancel), scoped to whichever account is open.

## Run

Needs a Redis instance reachable at `REDIS_URL` (defaults to `redis://localhost:6379`):

```bash
cd server && npm install && npm start
```

```bash
cd client && npm install && npm run dev
```

Open `http://localhost:5173`. The Vite dev server proxies `/api/*` to the backend on port 4000.

### Docker

```bash
docker compose up -d --build
```

Open `http://localhost:5050`. This starts three containers: `redis` (session tokens), `server`, and `client`. Saved accounts persist in `./server/data/accounts.json` (mounted as a volume); connection state persists in the `redis_data` Docker volume. Set `ACCOUNTS_ENC_KEY` in the environment to control the encryption key (defaults to a dev secret — set your own for anything beyond local use).

## Notes

- IPO list distinguishes `ongoing` / `closed` (from the `status` field) and disables **Apply** for anything not currently open.
- The Apply form supports multiple bids up to each instrument's `max_bid_count`, and lets you choose a fixed price instead of cutoff when the instrument allows it.
- Applications can be cancelled while their status is `submitted`.
- Credentials (including the TOTP secret) are stored encrypted on the server's disk, not in the browser. There's no login gate on the dashboard itself — anyone who can reach the server can manage accounts and apply/cancel IPOs, same as the earlier single-session design. Treat this as a personal/local tool, not something to expose publicly.
