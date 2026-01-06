# React Dashboard

This directory contains the React-based dashboard for Refresherr.

## Development

```bash
npm install
npm start
```

The development server will start on http://localhost:3000 and proxy API requests to the backend at http://localhost:8088.

## Building for Production

```bash
npm run build
```

This creates an optimized production build in the `build/` directory. The backend will serve these static files from the `/static` route (when integrated).

## API Endpoints

The dashboard consumes the following API endpoints:

- `/api/config` - Configuration data (scan roots, relay settings, etc.)
- `/api/routes` - Routing and path mapping configuration
- `/api/stats` - Symlink health statistics
- `/api/broken` - List of broken symlinks
- `/api/movies` - Movie library data
- `/api/episodes` - Episode library data

## Integration

The React app is designed to be served as static assets by the FastAPI/Flask backend in a unified container deployment. The build output will be served from `/static` and the backend will handle all API routes.
