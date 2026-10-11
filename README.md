# Report Parser

A Flask-based web application for reviewing Android Tradefed certification ZIP archives and turning the embedded `test_result.xml` data into a single, human-readable dashboard.

This tool is designed for Android certification workflows, where teams often receive multiple ZIP packages from CTS/GTS/TVTS/STS/VTS/Verifier jobs and need a quick way to group results, identify mismatches, and review failed test cases without manually opening every archive.

## What the tool does

- Upload one or more ZIP files.
- Recursively inspect nested ZIP files.
- Search for `test_result.xml` files.
- Parse Tradefed result metadata and per-module/per-test-case data.
- Merge repeated or split reports for the same build/suite.
- Detect when inputs belong to different build fingerprints.
- Save the latest successful analyses in SQLite.
- Show a dashboard in the browser and allow download as standalone HTML.

## Scope and assumptions

This is not a general-purpose XML parser. It is purpose-built around Tradefed `test_result.xml` output, including fields like:

- suite information
- module states
- pass/fail/assumption-failure/ignored status
- build fingerprint and security patch info
- Android version and SDK metadata

The parser intentionally avoids silently combining results from different builds. If multiple uploaded reports have different build fingerprints, the dashboard marks the run as a build mismatch and suppresses aggregate test metrics.

## Repository layout

```text
Report_Parser/
├── app.py                 # Flask app and routes
├── parser.py              # ZIP/XML scan, parse, merge, and build validation logic
├── history.py             # SQLite-based analysis history
├── report_builder.py      # HTML dashboard renderer
├── start.sh               # Local bootstrap and startup script
├── Jenkinsfile            # CI/CD pipeline definition
├── gunicorn.conf.py       # Gunicorn runtime settings
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment configuration
├── .gitignore
├── templates/
│   └── index.html         # Main web UI
├── static/
│   ├── app.js             # Front-end behavior
│   └── style.css          # Styles for the dashboard and UI
├── deploy/
│   ├── install-server.sh  # Linux server provisioning script
│   ├── report-parser-deploy.sh
│   └── report-parser.service
├── data/                  # Created at runtime for SQLite database
└── README.md
```

## Technologies

- Python 3.10+
- Flask 3.x
- Gunicorn
- SQLite
- HTML/CSS/JavaScript for the browser UI

## Requirements

- Python 3.10 or newer
- Git
- A modern browser

The app does not require a separate database server. SQLite is created automatically in the repository under `data/gct_report_parser.db` when the app runs.

## Local quick start

Clone and run:

```bash
git clone https://github.com/bhanuroyal002/Report_Parser.git
cd Report_Parser
./start.sh
```

`start.sh` will:

1. check for Python 3.10+
2. create `.venv` if needed
3. install dependencies from `requirements.txt`
4. reuse the existing environment if already present
5. start the app locally on `http://127.0.0.1:8080`

For later runs:

```bash
./start.sh
```

## Running directly

If you want to run the Flask app manually:

```bash
python app.py
```

Or:

```bash
HOST=127.0.0.1 PORT=8080 python app.py
```

This is suitable for local development, but not for production deployment.

## Production deployment

For a shared server, the repository is set up to run using Gunicorn behind a systemd service.

### 1. Provision the server

```bash
sudo bash deploy/install-server.sh
```

This script:

- creates/updates the app directory under `/opt/report_parser`
- clones or pulls the repo
- creates a virtual environment
- installs Python requirements
- copies `.env.example` to `.env`
- sets `HOST=0.0.0.0` and `PORT=8080`
- installs the `report-parser.service` systemd unit
- enables and starts the service

### 2. Runtime service

The service definition is installed at:

```text
/etc/systemd/system/report-parser.service
```

It runs the app with Gunicorn using the config in `gunicorn.conf.py`.

### 3. Smoke check

The app is expected to be reachable on:

```text
http://<server-ip>:8080
```

The Jenkins pipeline also runs a smoke test by curling `/` after deployment.

## Configuration

The app reads configuration from environment variables. Example values are in `.env.example`:

```dotenv
HOST=127.0.0.1
PORT=8080
DEBUG=false
DATABASE_PATH=data/gct_report_parser.db
MAX_FILE_SIZE_MB=500
MAX_REQUEST_SIZE_MB=1024
MAX_ZIP_DEPTH=20
```

### Meaning of the key settings

- `HOST`: bind address for Flask or Gunicorn
- `PORT`: application port
- `DEBUG`: enable Flask debug mode
- `DATABASE_PATH`: SQLite database path
- `MAX_FILE_SIZE_MB`: maximum size of an individual zip file upload
- `MAX_REQUEST_SIZE_MB`: maximum size of the request payload
- `MAX_ZIP_DEPTH`: maximum nested zip recursion depth

## Web app behavior

When the app is running, the browser UI allows the user to:

- upload report ZIPs
- start report analysis
- view summary metrics
- review incomplete modules
- review failed test cases
- view dashboard data and historical runs
- download the generated HTML dashboard

## API endpoints

The app exposes a small set of JSON endpoints:

- `GET /` — serves the main UI
- `GET /api/dashboard` — returns the empty/default dashboard payload
- `GET /api/history` — returns the last N analyses in SQLite
- `GET /api/history/<run_id>` — returns a specific historical report by run ID
- `POST /api/analyze` — accepts uploaded ZIP files and returns parsed dashboard data
- `POST /api/publish` — accepts a dashboard JSON object and returns standalone HTML

## Result semantics and mismatch handling

The parser follows a practical certification workflow:

- results from the same build fingerprint are merged together
- repeated executions of the same testcase reconcile using pass-priority logic
- if a testcase passes in any execution, the final state is considered PASS
- if reports contain multiple different build fingerprints, the tool flags this as a build mismatch
- in that case, the overall pass/fail summary is intentionally suppressed to avoid misleading aggregate results

Examples of reconciliation behavior implemented in the parser:

- PASS + FAIL -> PASS
- FAIL + PASS -> PASS
- PASS + PASS -> PASS
- FAIL + FAIL -> FAIL

## History and persistence

The app stores the most recent 20 successful analysis runs in SQLite. The history includes:

- run ID
- analysis timestamp
- status
- build fingerprint
- Android version
- security patch
- suite count
- total tests
- passed/failed counts
- full dashboard JSON payload

The database is stored in:

```text
data/gct_report_parser.db
```

The directory is auto-created if it does not exist.

## CI/CD

The included `Jenkinsfile` does the following:

1. checks out the repo
2. verifies Python syntax and required files exist
3. creates a CI virtualenv
4. installs dependencies
5. packages the repo into a tarball
6. deploys via the server installer entrypoint
7. smoke-tests the deployed app through HTTP

## Known limitations

- This parser is tuned for Tradefed `test_result.xml` content and may not correctly interpret completely different XML schemas.
- It expects report ZIPs and nested ZIP archives to be valid and readable.
- It is designed for internal/corporate deployment patterns; it does not include enterprise auth or RBAC.
- Historical analysis should be treated as operational data, not an external system of record.
- No license is currently specified for the repository.

## Troubleshooting

### App does not start

Check Python version:

```bash
python3 --version
```

Make sure the requirements are installed:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

### No reports recognized

Verify that the uploaded ZIP contains a file ending in `test_result.xml` inside the archive or nested inside another ZIP.

### Build mismatch warning

This is expected behavior when different uploaded reports belong to different build fingerprints. This is treated as a data-quality issue, not a parser failure.

## License

No license has been specified for this repository yet.

## Summary

This repository is a focused internal tool for parsing Android certification ZIP results and presenting them in a single dashboard. It is already structured for local execution, Linux server deployment, and CI/CD-based deployment, but it is still best understood as a specialized analysis workflow tool rather than a generic enterprise product.

If you want, the next step would be to tighten the documentation around actual usage examples and add a proper sample dashboard screenshot or a sample report upload workflow.
