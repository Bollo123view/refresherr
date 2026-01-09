# Refresherr Dashboard

This is the Vite-based React dashboard for Refresherr. The built assets are copied
into the container during the Docker build and served by the Flask dashboard API.

## Local development

```bash
npm install
npm run dev
```

By default the app expects the Refresherr API on `http://localhost:8088`.

## Build

```bash
npm run build
```

The build output is written to `dist/`.
