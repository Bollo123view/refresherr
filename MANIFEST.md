# Refresherr Repository Cleanup - File Manifest

This manifest documents all files and folders that were removed, changed, or kept as part of the repository cleanup and consolidation effort.

## Summary

- **Total Files Removed:** 17
- **Total Files Changed:** 3
- **Total Files Added:** 2
- **Net Change:** -3,628 lines of code (consolidation and cleanup)

---

## Files Removed

### Documentation (Consolidated into README.md)
1. `DASHBOARD_UX_GUIDE.md` - Dashboard usage documentation
2. `DEPLOYMENT.md` - Deployment guide
3. `USAGE_EXAMPLES.md` - Usage examples
4. `IMPLEMENTATION_SUMMARY.md` - Implementation notes
5. `IMPLEMENTATION_DELIVERABLES.md` - Deliverables documentation

### Dockerfiles (Replaced with Single Unified Dockerfile)
6. `app/Dockerfile` - Scanner service Dockerfile
7. `services/dashboard/Dockerfile` - Dashboard service Dockerfile
8. `services/research-relay/Dockerfile` - Relay service Dockerfile

### Configuration
9. `docker-compose.yml` - Multi-service docker-compose (replaced with single-service version)

### Scripts
10. `scripts/clean_symlinks.sh` - Utility script
11. `scripts/symlink_scanner.sh` - Utility script

### Backup/Temporary Files
12. `replacements.txt` - Token replacement file (no longer needed)

### Templates (Override Directory)
13. `override/templates/broken.html` - Template override
14. `override/templates/episodes.html` - Template override
15. `override/templates/index.html` - Template override
16. `override/templates/movies.html` - Template override

### Directories Removed
- `scripts/` - Utility scripts directory
- `override/` - Template overrides directory

---

## Files Changed

### Documentation
1. **`README.md`** - Completely rewritten
   - Consolidated all documentation into single comprehensive guide
   - Added single-container deployment instructions
   - Included security and isolation notes
   - Added complete API reference
   - Simplified configuration examples
   - **Before:** 1,128 lines
   - **After:** ~500 lines (streamlined)

### Configuration
2. **`config/env.sample`** - Updated for single-container architecture
   - Changed `RELAY_BASE` from `http://research-relay:5050` to `http://127.0.0.1:5050`
   - Changed `RELAY_TOKEN` default from `REPLACE-WITH-YOUR-SECRET-TOKEN` to `internal`
   - Added Sonarr/Radarr configuration examples
   - Added CineSync configuration examples
   - Updated documentation notes

---

## Files Added

### Docker Infrastructure
1. **`Dockerfile`** (New) - Unified single-container Dockerfile
   - Multi-stage build with React dashboard compilation
   - Combines scanner, dashboard API, and relay service
   - Single entrypoint script that starts all services
   - Healthcheck for monitoring
   - Based on Python 3.11-slim with tini for signal handling

2. **`docker-compose.yml`** (New) - Single-service docker-compose
   - Replaced 3-service architecture with 1 service
   - Simplified volume configuration
   - No internal networks needed
   - Security hardening options included (commented)

---

## Files Kept (Unchanged)

### Core Application Code
- `app/` - Scanner and core logic (all Python modules)
  - `app/refresher/` - Main application package
  - `app/cli.py` - CLI interface
  - `app/healthcheck.py` - Health check script
  - `app/requirements.txt` - Python dependencies
  
### Services (Code Kept, Dockerfiles Removed)
- `services/dashboard/` - Dashboard API and templates
  - `services/dashboard/app.py` - Flask application
  - `services/dashboard/api.py` - API endpoints
  - `services/dashboard/templates/` - HTML templates
  - `services/dashboard/requirements.txt` - Dependencies
  
- `services/research-relay/` - Relay service
  - `services/research-relay/app.py` - Flask relay application
  - `services/research-relay/requirements.txt` - Dependencies

### React Dashboard
- `dashboard/` - React frontend
  - `dashboard/src/` - React source code
  - `dashboard/public/` - Static assets
  - `dashboard/package.json` - NPM dependencies
  - `dashboard/package-lock.json` - Dependency lock
  - `dashboard/README.md` - Dashboard-specific docs

### Configuration
- `config/config.sample.yaml` - YAML configuration sample
- `config/config.yaml` - User YAML configuration (if exists)

### Project Files
- `LICENSE` - Project license
- `VERSION` - Version file
- `.gitignore` - Git ignore rules
- `.gitattributes` - Git attributes

---

## Architecture Changes

### Before (Multi-Container)
```
┌─────────────────────────────────────────────────────┐
│                  Docker Compose                     │
├─────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │  refresher   │  │  dashboard   │  │  relay   │ │
│  │  (scanner)   │  │  (API+UI)    │  │ (search) │ │
│  │  Port: None  │  │  Port: 8088  │  │Port: 5050│ │
│  └──────────────┘  └──────────────┘  └──────────┘ │
│         │                  │                │      │
│         └──────────────────┴────────────────┘      │
│         Shared: config/, data/, Internal HTTP      │
└─────────────────────────────────────────────────────┘
```

### After (Single Container)
```
┌────────────────────────────────────────────┐
│          Single Refresherr Container       │
├────────────────────────────────────────────┤
│  ┌────────────────────────────────────┐   │
│  │  Scanner (Background Process)      │   │
│  │  - Monitors symlinks               │   │
│  │  - Updates database                │   │
│  └────────────────────────────────────┘   │
│  ┌────────────────────────────────────┐   │
│  │  Dashboard API (Flask)             │   │
│  │  - REST API endpoints              │   │
│  │  - Serves static React UI          │   │
│  │  - Port: 8088 (exposed)            │   │
│  └────────────────────────────────────┘   │
│  ┌────────────────────────────────────┐   │
│  │  Relay Service (Internal)          │   │
│  │  - Sonarr/Radarr proxy             │   │
│  │  - Port: 5050 (localhost only)     │   │
│  │  - No authentication needed        │   │
│  └────────────────────────────────────┘   │
│                                            │
│  All components share process space       │
│  No internal HTTP calls needed            │
└────────────────────────────────────────────┘
```

---

## Benefits of Consolidation

### Simplified Deployment
- **Before:** 3 services, 3 Dockerfiles, internal networking
- **After:** 1 service, 1 Dockerfile, no networking complexity

### Reduced Configuration
- **Before:** Multiple service configurations, token management between services
- **After:** Single service, no internal tokens needed

### Enhanced Security
- **Before:** Internal HTTP communication with token authentication
- **After:** Direct function calls, no network exposure for internal components

### Easier Maintenance
- **Before:** 5+ documentation files, scattered information
- **After:** Single comprehensive README with all information

### User Experience
- **Before:** Edit 3 Dockerfiles and docker-compose.yml, manage service dependencies
- **After:** Fill out config.yaml and .env, run `docker-compose up -d`

---

## Migration Guide (For Existing Users)

If you're upgrading from the multi-container setup:

1. **Backup your data:**
   ```bash
   cp -r data/ data.backup/
   cp config/config.yaml config/config.yaml.backup
   cp .env .env.backup
   ```

2. **Update configuration:**
   - Change `RELAY_BASE` to `http://127.0.0.1:5050` in `.env`
   - Change `RELAY_TOKEN` to `internal` in `.env`

3. **Pull new changes:**
   ```bash
   git pull origin main
   ```

4. **Stop old services:**
   ```bash
   docker-compose down
   ```

5. **Rebuild and start:**
   ```bash
   docker-compose build
   docker-compose up -d
   ```

6. **Verify:**
   ```bash
   docker-compose ps
   curl http://localhost:8088/health
   ```

---

## Verification Checklist

- [x] Documentation consolidated into single README.md
- [x] Unnecessary documentation files removed
- [x] Scripts directory removed
- [x] Override directory removed
- [x] Backup files removed
- [x] Single Dockerfile created with multi-stage build
- [x] Single docker-compose.yml created
- [x] Old Dockerfiles removed
- [x] Configuration files updated for single-container mode
- [x] Architecture simplified to single container
- [x] Internal networking eliminated
- [x] Security enhanced (no internal HTTP/tokens)

---

**Date:** 2026-01-07
**Branch:** copilot/clean-repo-and-consolidate-docs
