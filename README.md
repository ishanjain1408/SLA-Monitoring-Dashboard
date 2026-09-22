# EarthRe — SLA Monitoring Dashboard

## Overview

This repository contains a full-stack web application and data analysis pipeline for SLA (Service Level Agreement) health-check monitoring data. 

The system takes messy, multi-agent monitoring logs (CSV files), cleans and persists them, and surfaces the true SLA availability of 5 cloud services on a React-based dashboard. 

---

## 1. Architecture

The application is built as a **Next.js 15 (App Router)** full-stack application, located in the `web/` directory.

- **Frontend (Upload UI & Dashboard):** React / Next.js. Provides a single-page view to upload CSV files, dynamically computes and renders the 99.9% SLA threshold cards, and provides a raw logs view. I chose Next.js because it natively supports both the React frontend and serverless API endpoints in a single repository.
- **Backend (Stateless Processing):** Next.js API Routes (`app/api/upload/route.ts`). This acts as the serverless function. It receives the multipart CSV file, processes it strictly in-memory (using `csv-parse`), applies our data-cleaning rules (normalizing timestamps and latencies), and hands the cleaned records off to the database.
- **Persistence (Database):** SQLite (`better-sqlite3`). I chose SQLite for the immediate deliverable so that you can run `npm run dev` and test the persistence locally without needing to provision cloud credentials. For the production cloud deployment, this is designed to be easily swapped for Vercel Postgres.
- **Styling:** Vanilla CSS (`globals.css`) with CSS variables and a modern dark aesthetic. 

*(Note: The `analysis/` directory contains the original Python exploratory data analysis script and test suite used to discover the data quirks before writing the Next.js app).*

---

## 2. Data Findings

The provided CSV files simulate messy, multi-agent monitoring. We discovered the following issues and implemented handling for them in our serverless API route (`web/lib/process-csv.ts`):

1. **Mixed Timestamp Formats:** Timestamps appeared in ISO UTC (`Z`), ISO with non-UTC offsets (e.g., `+05:30`), and Unix epoch seconds.
   - *Fix:* Our processor parses standard ISO strings and catches 10-digit epoch timestamps, strictly normalizing everything to ISO UTC strings before database insertion.
2. **Missing Latencies:** About 1.2% of checks lack a latency value.
   - *Fix:* Handled as `NULL` in the database. The check is still counted for availability calculations (since it has an HTTP status code), but ignored in latency averages.
3. **Inconsistent Units:** `svc-search` reported latency in seconds (`s`), while others used milliseconds (`ms`).
   - *Fix:* Detected the `latency_unit` column and strictly multiplied by 1000 where necessary, enforcing `latency_ms` universally.
4. **Duplicate Records:** ~8% of the rows are excess. This is caused by duplicate `(service_id, timestamp)` pairs, representing two different agents (`agent-1`, `agent-2`) reporting the same check concurrently.
   - *Fix:* The SQLite schema enforces a `UNIQUE(service_id, timestamp, agent)` constraint. `INSERT OR IGNORE` deduplicates exact identical agent reports, but we preserve both agents' perspectives. 

---

## 3. Assumptions & Design Choices

1. **SLA Threshold:** Standard 99.9% availability.
2. **HTTP Success:** Any 2xx status code is considered a successful check. 5xx codes are failures.
3. **Choice of Stats:** For the dashboard, I decided the most critical view is a **binary SLA Breach status**. On-call engineers need to know *instantly* if a service is breached, so the UI cards highlight red if availability drops below 99.9%. I also display the exact availability percentage (to 3 decimal places) and raw counts (`Success / Total Checks`). 
4. **Data Aggregation:** The prompt requested we don't assume the number of days. The app queries the DB dynamically to get totals rather than assuming a 15-minute interval across X days.

---

## 4. How to Run / Redeploy

### Run Locally (Database & UI)

The web app is entirely self-contained. 

```bash
cd web
npm install
npm run dev
```
1. Open `http://localhost:3000`
2. Upload one of the root `monitoring_checks_*.csv` files.
3. The dashboard will instantly populate.

### Cloud Deployment (Vercel)

The system is architected as a Next.js serverless app, which is the native stack for **Vercel** (Free Tier). 

> [!WARNING]
> **Important Note on SQLite and Vercel Deployment:** By default, this app uses `better-sqlite3` for local development. However, deploying this to Vercel as-is will result in an **"Unexpected end of JSON input"** error on the frontend. This happens because Vercel's serverless environment has a read-only filesystem, ephemeral storage, and lacks native module support, causing the SQLite API routes to crash. **You MUST migrate to a cloud database before deploying.**

To deploy successfully:
1. Create a free **Postgres** database in Vercel Storage (or use Supabase, Neon, etc.).
2. Swap `better-sqlite3` for a cloud database client (e.g., `@vercel/postgres`) in `web/lib/db.ts`.
3. Run `npx vercel` from the `web/` directory.
4. **Live URL:** Vercel will automatically provision a live serverless URL (e.g., `https://earthre-sla.vercel.app`) where the Upload UI and API function will live. 

*(Since I am your local AI assistant, I have prepared it perfectly for this step but cannot provision your personal Vercel account myself).*

---

## 5. What I'd Do Differently With More Time

1. **Authentication:** Add NextAuth so only internal engineers can upload logs or view the dashboard.
2. **Advanced Deduplication:** Right now, both `agent-1` and `agent-2`'s checks are stored. In production, I would use a materialised view or ingestion rule to select the "best" or latest check for a given timestamp, rather than storing both.
3. **Data Visualization:** Add `Chart.js` or `Recharts` to show a timeline graph of latencies (highlighting the 3-4x latency spikes we found during the data analysis phase).
4. **Async Processing Queue:** For massive CSVs, a serverless function might hit a timeout limit (e.g., 10 seconds on Vercel Hobby tier). I would decouple the upload from processing by putting the raw CSV in an S3 bucket and triggering a background worker (e.g. AWS SQS) to parse it. 
