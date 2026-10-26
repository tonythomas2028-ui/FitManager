# FitManager — Gym Management System

## Local setup (Windows PowerShell)
1. Extract the ZIP.
2. Open PowerShell in the `FitManager` folder.
3. Run:

```powershell
py -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:ADMIN_USERNAME = "admin"
$env:ADMIN_PASSWORD = "choose-a-local-password"
$env:SECRET_KEY = "local-development-secret-change-me"
flask --app app init-db
python app.py
```

Open http://127.0.0.1:5000
Login with the local username and password set above.
Health check: http://127.0.0.1:5000/health
Database readiness check: http://127.0.0.1:5000/ready
Stop with Ctrl+C.

The application uses development-only fallback values only when `APP_ENV` is not `production`. For production, set `APP_ENV=production` and explicitly configure `SECRET_KEY`, `ADMIN_USERNAME`, and `ADMIN_PASSWORD`. Never use development credentials in a deployed environment. Run `flask --app app init-db` once before starting the app; the application no longer creates tables automatically during import.

## Features
- Dashboard overview and expiring membership reminders
- Add, search and filter members
- Membership start/end dates and Active/Expired status
- Attendance check-ins (expired memberships are blocked)
- Payment records and revenue totals
- Member profile with attendance/payment history
- Admin login, liveness endpoint (`/health`), and database readiness endpoint (`/ready`)

## Deployment
Recommended first: Render. Push the folder to GitHub, create a Render Web Service, and use:
- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:app`
- Health check: `/health`

Set `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `DATABASE_URL` in Render environment settings. Local SQLite is for development. For persistent hosted data, configure PostgreSQL and set `DATABASE_URL` to its connection string. Render free web services have ephemeral local storage; its free PostgreSQL plan currently expires after 30 days, so check current plan terms.

Vercel also supports Flask, but use an external PostgreSQL database for persistent records; do not depend on a local SQLite file on serverless hosting.

This is a college-project starter. Change the demo credentials before deploying and don't use it for real member data without additional security hardening.

## Obsidian Pro UI refresh
The refreshed UI uses a dark charcoal surface system, electric-purple primary actions, higher-contrast tables and forms, and responsive navigation for mobile screens. This refresh changes the presentation layer (`static/style.css` and `templates/base.html`) while preserving the existing Flask routes, models, and application logic.
### Login page artwork
The login hero uses `static/gym-motivation.jpg`, based on the gym motivation image supplied for this project. Replace that file to change the artwork; no backend or route changes are needed.
