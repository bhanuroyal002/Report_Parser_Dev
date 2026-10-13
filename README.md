# GCT Insight — Android Certification Report Parser

GCT Insight is a Flask web application for analyzing Android Tradefed certification result ZIP files. It brings test progress, outcome counts, build identity, incomplete modules, and failures into one browser-based dashboard.

Repository: [bhanuroyal002/Report_Parser_Dev](https://github.com/bhanuroyal002/Report_Parser_Dev)

## What it does

- Accepts one or more ZIP archives in a single analysis.
- Finds Tradefed `test_result.xml` files inside uploaded ZIPs, including nested ZIP archives.
- Detects the test suite from XML `suite_name` and `suite_plan` metadata, including CTS-on-GSI and CTS Verifier mappings.
- Summarizes suite completion, module progress, test outcomes, failures, and build metadata such as fingerprint, Android release, and security patch.
- Identifies incomplete modules and failed test cases for follow-up.
- Combines compatible reports and reconciles repeated test records.
- Detects inconsistent build fingerprints and avoids presenting potentially misleading aggregate test totals for mismatched builds.
- Saves recent analysis runs in SQLite and lets users reopen prior results.
- Exports a standalone HTML dashboard that can be viewed or shared separately from the web application.
- Exposes a health endpoint for deployment smoke tests and monitoring.

## How report analysis works

1. Select one or more report ZIP files in the web interface.
2. Choose **Analyze Reports** to upload the selected files and start parsing.
3. The application scans the ZIP contents and nested archives for supported Tradefed result XML.
4. The parser reads suite, module, test, and build information, then merges compatible results.
5. The dashboard shows suite progress, outcome counts, build details, incomplete modules, and failures.
6. Use **View Dashboard** or **Download Dashboard HTML** to view or save a standalone report. Successful analyses are also available from recent history.

### Build identity and merge behavior

- Reports with compatible build identity can be combined.
- If uploaded results have different known build fingerprints, the dashboard marks a build mismatch and suppresses combined test metrics that could be misleading.
- If a test is repeated across compatible reports, a passing execution takes precedence over a failing execution in the merged result.
- A report is interpreted as Android Tradefed output. Arbitrary XML formats are not guaranteed to be supported.

## Technology stack

| Area | Technology |
|---|---|
| Application | Python 3.10+, Flask |
| Production server | Gunicorn |
| Report parsing | Python ZIP handling and streaming XML parsing |
| History storage | SQLite |
| Front end | HTML, CSS, JavaScript |
| Containerization | Docker, Docker Compose |
| CI/CD | Jenkins pipeline |
| Deployment monitoring | systemd timer and health-check script |

## Repository layout

```text
Report_Parser_Dev/
├── app.py                              # Flask routes, uploads, API, and health endpoint
├── parser.py                           # Tradefed XML/ZIP parsing, merge, and build checks
├── history.py                          # SQLite persistence for recent analysis runs
├── report_builder.py                   # Standalone HTML dashboard generator
├── templates/
│   └── index.html                      # Main application page
├── static/
│   ├── app.js                          # Dashboard and upload interactions
│   └── style.css                       # UI styling
├── tests/
│   ├── test_app.py                     # Flask endpoint tests
│   └── test_parser.py                  # Parser regression tests
├── deploy/
│   ├── install-server.sh               # Initial Linux/Docker setup
│   ├── report-parser-deploy.sh         # Deployment and rollback logic
│   ├── report-parser-healthcheck.sh    # Health-state monitor and notifications
│   ├── report-parser-healthcheck.service
│   └── report-parser-healthcheck.timer
├── Dockerfile                          # Image build; runs regression tests
├── docker-compose.yml                  # Container configuration
├── Jenkinsfile                         # CI/CD pipeline
├── gunicorn.conf.py                    # Production server settings
├── requirements.txt                    # Python dependencies
├── start.sh                            # Local environment setup and startup
├── .env.example                        # Example application settings
├── .dockerignore
└── README.md
```

## Run locally

### Prerequisites

- Python 3.10 or newer
- Git
- A modern browser

### Quick start

```bash
git clone https://github.com/bhanuroyal002/Report_Parser_Dev.git
cd Report_Parser_Dev
chmod +x start.sh
./start.sh
```

The helper creates a local `.venv` if required, installs `requirements.txt` when dependencies change, and starts the app using the configured host and port. By default, open:

- Application: [http://127.0.0.1:8080](http://127.0.0.1:8080)

Stop the application with `Ctrl+C`.

### Manual setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

The SQLite database is initialized automatically when the app starts. Its default local path is `data/gct_report_parser.db`.

## Configuration

Copy the sample file before configuring local settings:

```bash
cp .env.example .env
```

The app loads environment variables from the process environment. Docker Compose reads the optional `.env` file and passes its configured variables to the container.

| Variable | Purpose | Default |
|---|---|---|
| `HOST` | Address for the application server | `127.0.0.1` locally; `0.0.0.0` in Docker |
| `PORT` | HTTP port | `8080` |
| `DEBUG` | Enable Flask debug mode when running `app.py` directly | `false` |
| `DATABASE_PATH` | SQLite database file | `data/gct_report_parser.db` locally; `/app/data/gct_report_parser.db` in Docker |
| `MAX_FILE_SIZE_MB` | Maximum size of an individual uploaded ZIP; `0` disables this application-level cap | `0` |
| `MAX_REQUEST_SIZE_MB` | Maximum total request size; `0` disables Flask's configured request cap | `0` |
| `MAX_ZIP_DEPTH` | Maximum nested ZIP depth scanned | `20` |
| `MAX_ZIP_ENTRY_MB` | Maximum expanded size of a relevant ZIP entry; `0` disables this cap | `0` |
| `MAX_TOTAL_UNCOMPRESSED_MB` | Maximum combined expanded data per analysis; `0` disables this cap | `0` |
| `MAX_ZIP_ENTRIES` | Maximum ZIP entries scanned per analysis; `0` disables this cap | `0` |
| `WEB_CONCURRENCY` | Number of Gunicorn workers in the Docker configuration | `2` |
| `GUNICORN_TIMEOUT` | Gunicorn worker timeout in seconds | `900` |
| `GUNICORN_LOG_LEVEL` | Gunicorn log verbosity | `info` |
| `GUNICORN_WEBHOOK_URL` | Not used by the current application code | — |
| `REPORT_PARSER_WEBHOOK_URL` | Optional Jenkins and health-monitoring notification destination, configured in their respective runtime environments | Unset |

**Large uploads:** A zero limit disables only that specific application-level limit. It does not remove operating-system, proxy, network, timeout, temporary-storage, or memory constraints. Large and deeply nested archives should be tested against the resources and timeouts of the actual deployment before being used in production.

Do not commit real `.env` files, credentials, database contents, or webhook URLs containing secrets.

## Use Docker Compose

Docker Compose is available for local/container testing. The checked-in Compose configuration maps port 8080 and mounts the deployment data directory at `/opt/report_parser/data`.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f report-parser
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). To stop the container:

```bash
docker compose down
```

**Note:** The Compose file uses the host path `/opt/report_parser/data` for persistent storage, which is tailored to the shared-server deployment. On a machine where that path is unsuitable, change the volume mapping to a local directory before starting Compose. Back up persistent data before removing or replacing a deployment.

## HTTP API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Serve the main dashboard |
| `GET` | `/healthz` | Check application/database readiness |
| `GET` | `/api/dashboard` | Return an empty/default dashboard structure |
| `GET` | `/api/history` | List recent stored analyses |
| `GET` | `/api/history/<run_id>` | Retrieve a previous analysis |
| `POST` | `/api/analyze` | Analyze uploaded ZIP files (multipart field: `files`) |
| `POST` | `/api/publish` | Generate a downloadable HTML dashboard from dashboard JSON |

### Health check

`GET /healthz` returns HTTP 200 when the app can query SQLite:

```json
{"status":"healthy","database":"ok"}
```

If the database check fails, it returns HTTP 503 with an unhealthy status.

## History and generated reports

The application stores up to **20 recent analyses** in SQLite. Older entries are removed as new analyses are saved. The default local data file is:

```text
data/gct_report_parser.db
```

The shared deployment uses `/opt/report_parser/data` on the host, mounted inside the container. Back up this directory if the history must be retained. The standalone HTML export is separate from the stored history and can be saved or shared as needed.

## Tests and validation

Install dependencies and run the regression suite:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The test suite covers application endpoints and core parser cases, including nested ZIP discovery, build-fingerprint mismatch handling, incomplete modules, invalid ZIPs, and upload-size behavior. The Docker build runs the regression tests before the image is finalized.

## CI/CD and server deployment

The `Jenkinsfile` defines the repository pipeline:

1. Check out the selected source revision.
2. Validate Python syntax, shell syntax, and required deployment files.
3. Package source while excluding Git data, virtual environments, local database data, `.env`, and generated Python cache files.
4. Archive the build package in Jenkins.
5. Invoke the server deployment helper using `sudo`.
6. Smoke-test `/healthz` and the home page.
7. Optionally send a JSON webhook notification for success or failure.

The deployment script builds a versioned Docker image, updates the `report-parser-container` container, preserves `.env` and `data/`, and checks application health. If the newly started container does not become healthy, it attempts to restore the previous image/container.

The expected server helper is `/usr/local/sbin/report-parser-deploy`; the Jenkins agent must have the necessary permission to run it. The deployment listens on port 8080. Initial server setup is supported by `deploy/install-server.sh`.

Useful commands on the deployment host:

```bash
docker ps --filter name=report-parser-container
docker logs --tail 100 report-parser-container
curl -i http://127.0.0.1:8080/healthz
curl -I http://127.0.0.1:8080/
```

Avoid running a second application service on port 8080 alongside the Docker deployment.

## Health monitoring and notifications

The deployment includes a systemd service and timer intended to run the health-check script every five minutes. The monitor records its last observed state and sends a notification when it transitions to unhealthy or recovers.

For the health monitor, configure the optional webhook URL in the environment available to the systemd health-check service, using a protected environment file such as `/etc/report-parser-monitoring.env`:

```dotenv
REPORT_PARSER_WEBHOOK_URL=https://your-webhook-endpoint
```

Protect any file containing a real endpoint or secret:

```bash
sudo chmod 600 /etc/report-parser-monitoring.env
```

Configure `REPORT_PARSER_WEBHOOK_URL` in Jenkins separately if pipeline notifications are required. The destination must accept a JSON payload with a `text` field. Notification failures are logged as warnings and do not by themselves determine whether the application deployment succeeded.

## Troubleshooting

### The application does not start

```bash
python3 --version
docker logs --tail 100 report-parser-container
curl -i http://127.0.0.1:8080/healthz
```

Inspect application logs, environment values, database-directory permissions, and port 8080 conflicts.

### No supported reports are found

Confirm that the ZIP contains a Tradefed `test_result.xml`, directly or inside a nested ZIP. The parser does not promise compatibility with unrelated report formats.

### The dashboard reports a build mismatch

Inspect the build fingerprints in the uploaded reports. Reports from different builds are deliberately not combined into misleading aggregate totals.

### A module is shown as incomplete

Check the module's completion state in the Tradefed XML. Modules marked `done=false` are highlighted for review.

### A large upload fails or times out

Review the application upload caps, ZIP scanning limits, reverse-proxy/client request limits, Gunicorn timeout, available disk space, and memory. Disabling a size cap does not guarantee that an arbitrarily large archive can be processed.

### The app is healthy but notifications are missing

Check that the webhook URL is configured in the correct runtime environment (Jenkins for pipeline messages; the systemd service environment for periodic health notifications), and inspect the Jenkins/service logs. Notifications depend on the endpoint being reachable and accepting the expected JSON payload.

## Known limitations

- The parser is designed for Android Tradefed `test_result.xml`; other XML schemas are not guaranteed.
- Build mismatch handling intentionally suppresses aggregate test metrics when different known build fingerprints are present.
- Setting upload or ZIP limits to zero disables application-level limits but does not remove infrastructure constraints or guarantee support for archives larger than 1 GB.
- The application does not currently implement enterprise authentication or role-based access control. Restrict access appropriately before exposing it beyond a trusted network.
- SQLite history is bounded to 20 recent analyses and needs backup if it is operationally important.
- No open-source license is currently specified in the repository.

## Security recommendations

- Keep the service behind appropriate network controls; the app currently does not provide user authentication.
- Keep secrets and production data out of source control.
- Configure conservative upload/ZIP limits when processing untrusted files.
- Monitor application logs, container health, disk capacity, and system memory.
