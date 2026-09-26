# TailWatch project website

This branch holds only the static marketing/landing page for the TailWatch
project (see the `main`-line development branch for the actual firmware).
Plain HTML/CSS, no build step, no framework.

## Deploying to Cloudflare Pages

1. Cloudflare dashboard -> **Workers & Pages** -> **Create application** -> **Pages** -> **Connect to Git**.
2. Select this repository.
3. Set the **Production branch** to `website`.
4. Build settings: **Framework preset** = `None`, **Build command** = (leave empty), **Build output directory** = `/`.
5. Deploy. Every push to `website` redeploys automatically.

## Files

- `index.html` -- the page
- `styles.css` -- all styling
- `favicon.svg`
