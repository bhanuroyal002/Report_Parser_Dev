# GCT Insight — Android Certification Report Parser

GCT Insight is a Flask web application that parses Android Tradefed certification report ZIP files and presents the results in a single dashboard. It is intended for QA teams reviewing CTS, GTS, STS, TVTS, VTS, CTS-on-GSI, and CTS Verifier results.

## Features

- Upload one or more report ZIP files for analysis.
- Discover `test_result.xml` files inside ZIP archives, including nested ZIPs.
- Summarize test outcomes, suites, modules, and build metadata.
- Highlight incomplete modules and failed test cases.
- Merge compatible reports and reconcile repeated test results.
- Detect different build fingerprints and avoid misleading combined totals.
- Store recent successful analyses in SQLite and reopen previous runs.
- Export a standalone HTML dashboard.
- Provide application/database health checks for deployment monitoring.

## How results are interpreted

- Reports with matching build identity can be combined.
- When a test case has repeated results, a passing execution takes priority over a failing execution.
- If uploaded reports contain different build fingerprints, the dashboard flags a build mismatch and suppresses aggregate metrics that could be misleading.
- The parser is designed for Android Tradefed `test_result.xml` output. Other XML formats are not guaranteed to be recognized.

## Technology stack

- Python 3.10+
- Flask
- Gunicorn
- SQLite
- HTML, CSS, and JavaScript
- Docker for the shared-server runtime
- Jenkins for CI/CD

## Repository structure

```text
Report_Parser/
├── app.py                         # Flask routes, upload handling, feedback, health check
├── parser.py                      # ZIP discovery, XML parsing, merge and build validation
├── history.py                     # SQLite history storage
├── report_builder.py              # Standalone HTML report generation
├── templates/                     # Main UI and feedback page
├── static/                        # Browser JavaScript and CSS
├── tests/                         # Parser and application regression tests
├── deploy/
│   ├── install-server.sh           # Linux host provisioning
│   ├── report-parser-deploy.sh     # Docker deployment and rollback
│   ├── report-parser-healthcheck.sh
│   ├── report-parser-healthcheck.service
│   └── report-parser-healthcheck.timer
├── Dockerfile                     # Image build and regression test execution
├── docker-compose.yml             # Docker Compose configuration
├── Jenkinsfile                    # CI/CD pipeline
├── gunicorn.conf.py               # Gunicorn runtime settings
├── requirements.txt               # Python dependencies
├── start.sh                       # Local setup and startup helper
├── .env.example                   # Example environment variables
└── README.md
```

## Run locally

### Prerequisites

- Python 3.10 or newer
- Git
- A modern web browser

### Start the application

```bash
git clone https://github.com/bhanuroyal002/Report_Parser.git
cd Report_Parser
./start.sh
```

The startup script creates a local virtual environment if needed, installs dependencies, and starts the application at:

- App: http://127.0.0.1:8080

To start manually instead:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The local SQLite database is created automatically. The default path is `data/gct_report_parser.db`.

## Configuration

Copy `.env.example` to `.env` and change values as required. Never commit real credentials or tokens.

| Variable | Purpose | Default |
|---|---|---|
| `HOST` | Application bind address | `127.0.0.1` |
| `PORT` | Application port | `8080` |
| `DEBUG` | Flask debug mode | `false` |
| `DATABASE_PATH` | SQLite database path | `data/gct_report_parser.db` |
| `MAX_FILE_SIZE_MB` | Maximum size of each uploaded file in MB; `0` disables the app-level limit | `0` |
| `MAX_REQUEST_SIZE_MB` | Maximum total request size in MB; `0` disables the Flask request limit | `0` |
| `MAX_ZIP_DEPTH` | Maximum nested ZIP depth | `20` |
| `MAX_ZIP_ENTRY_MB` | Maximum expanded size of a relevant ZIP entry in MB; `0` disables this limit | `0` |
| `MAX_TOTAL_UNCOMPRESSED_MB` | Maximum expanded data per analysis in MB; `0` disables this limit | `0` |
| `MAX_ZIP_ENTRIES` | Maximum ZIP entries scanned per analysis; `0` disables this limit | `0` |

A value of `0` disables the corresponding application-level size/count limit. This does **not** guarantee that arbitrarily large archives can be processed safely: the server still needs enough disk space and memory, and any reverse proxy or client timeout may impose its own limits. Relevant XML and nested ZIP entries can consume substantial memory during analysis. Files larger than 1 GB have not been guaranteed by a documented end-to-end stress test.

On the shared server, the deployment helper preserves `/opt/report_parser/.env` and `/opt/report_parser/data/` across deployments. Keep these outside source control.

## Web interface workflow

1. Open the application.
2. Select one or more Android certification report ZIP files.
3. Start analysis.
4. Review build identity, suite/module progress, test outcomes, incomplete modules, and failures.
5. Reopen a previous run from history if needed.
6. Download the generated standalone HTML report when a portable copy is required.

## HTTP endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Main dashboard |
| `GET` | `/healthz` | Application and SQLite health probe |
| `GET` | `/api/dashboard` | Empty/default dashboard payload |
| `GET` | `/api/history` | List stored analysis runs |
| `GET` | `/api/history/<run_id>` | Retrieve a stored run |
| `POST` | `/api/analyze` | Analyze uploaded ZIP files |
| `POST` | `/api/publish` | Generate standalone HTML from dashboard JSON |

### Health check

A healthy response from `GET /healthz` is HTTP 200:

```json
{"status":"healthy","database":"ok"}
```

If the database check fails, the endpoint returns HTTP 503. Jenkins checks this endpoint and the home page after deployment.

## History and data retention

Successful analysis runs are stored in SQLite. The history store retains up to 20 recent runs. The default local database path is:

```text
data/gct_report_parser.db
```

The deployed server uses a persistent data directory at `/opt/report_parser/data`, mounted into the application container. Back up this directory if the analysis history must be retained.

## Testing

Run the regression tests locally:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The Docker image build also runs the project's regression tests. Jenkins performs syntax/configuration checks, packages the source, deploys the image, and smoke-tests the health endpoint and home page.

## CI/CD and deployment

The `Jenkinsfile` pipeline:

1. Checks out the selected repository revision.
2. Validates Python and shell syntax and required deployment files.
3. Packages source while excluding Git history, virtual environments, local data, secrets, and generated Python cache files.
4. Invokes the server-side deployment helper.
5. Checks the deployed health endpoint and home page.
6. Can send a JSON webhook notification when `REPORT_PARSER_WEBHOOK_URL` is configured in Jenkins.

The server-side helper at `/usr/local/sbin/report-parser-deploy` invokes the repository deployment script. The application runs in Docker as `report-parser-container` and listens on port 8080. Deployment checks health and attempts to restore the previous container image if the new image fails its health check.

Useful deployment commands on a host with Docker access:

```bash
docker ps --filter name=report-parser-container
docker logs --tail 100 report-parser-container
curl -i http://127.0.0.1:8080/healthz
curl -I http://127.0.0.1:8080/
```

Do not run a separate legacy application service on port 8080 alongside the Docker deployment.

## Health monitoring and notifications

The deployment installs a systemd timer that runs the health check every five minutes. The monitor tracks health-state changes and is intended to avoid repeated notifications for an unchanged failure state.

For monitoring notifications, an administrator can create `/etc/report-parser-monitoring.env` as root:

```dotenv
REPORT_PARSER_WEBHOOK_URL=https://your-webhook-endpoint
```

Protect the file:

```bash
sudo chmod 600 /etc/report-parser-monitoring.env
```

The endpoint must accept a JSON payload containing a `text` field. Configure `REPORT_PARSER_WEBHOOK_URL` in Jenkins separately if build/deployment notifications are also required. Notification failures are logged as warnings and should not be treated as proof that the application deployment failed.

## Troubleshooting

### Application does not start

```bash
python3 --version
docker logs --tail 100 report-parser-container
curl -i http://127.0.0.1:8080/healthz
```

Check the container logs, environment configuration, database directory permissions, and whether port 8080 is already in use.

### No report XML files are found

Confirm that the ZIP contains a Tradefed `test_result.xml`, either directly or inside a nested ZIP. Other report formats may not be supported.

### Build mismatch is reported

Check that the uploaded reports belong to the same build. Different build fingerprints are deliberately not combined into one aggregate result.

### Upload or parsing fails for a large archive

Check available disk space and memory, application logs, and request-size/time limits in any proxy in front of the application. Disabling application-level limits does not remove infrastructure limits or memory requirements.

## Known limitations

- Input parsing is specialized for Android Tradefed `test_result.xml` files.
- Large expanded XML or nested ZIP entries can require substantial memory; unlimited size settings are not a substitute for load testing.
- The application does not currently provide enterprise authentication or role-based access control; deploy it only in an appropriately protected environment.
- SQLite history is operational application data and should be backed up if required.
- The repository does not currently specify an open-source license.

## Security notes

- Keep `.env`, database files, API tokens, and webhook URLs containing secrets out of Git.
- Restrict network access to the application and Jenkins according to your organization's policies.
- Review upload limits and available resources before exposing the service to untrusted users.
