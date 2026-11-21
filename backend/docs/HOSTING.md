# Hosting KRONOS from this Mac

```bash
cd kronos-backend
./scripts/host.sh        # builds the site, starts API + site behind an access code, opens a public tunnel
./scripts/stop_host.sh   # closes the tunnel, returns the API to local development mode
```

`host.sh` prints the public link (`https://….trycloudflare.com`) and the access code. Both are saved in
`data/host_url` and `data/host_access_code`; that folder is git-ignored. To use your own code, run
`KRONOS_ACCESS_CODE=YOUR-CODE ./scripts/host.sh`.

How it works:
- **One server for everything.** The Vite build (`kronos-app/dist`) is served by the FastAPI app itself (`KRONOS_STATIC_DIR`), so the site and `/api` share one address.
- **Access code.** Every path — website, API, `/docs` — needs the code (`KRONOS_ACCESS_CODE`). Visitors see a KRONOS login page. API calls without the code get `401`. The cookie stores a hash of the code (30 days, HttpOnly, Secure over https). Wrong codes are slowed down.
- **Public link.** A Cloudflare quick tunnel (`cloudflared`, free, no account) carries the public https link to `127.0.0.1:8000`. The Mac never opens a port to the internet.
- **Stays awake.** `caffeinate` keeps the Mac awake while the API runs.

Things to know:
- **The Mac must stay on, plugged in and online.** If the lid closes or the Mac sleeps, the site goes down.
- **The link changes every time `host.sh` starts a new tunnel.** For a permanent address, use a free Cloudflare account with a domain and a named tunnel (`cloudflared tunnel create kronos`).
- **AI answers come one at a time.** Each takes about 20–60 s on a 16 GB M4 and runs on the Mac. Everything else (cases, graph, temporal engine, evidence, ledger) is instant.
- **Local use while hosting.** Requests from this Mac itself (the dev site at `localhost:5173`, or `localhost:8000`) need no code. Only visitors coming through the Cloudflare link see the access-code page.
