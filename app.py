import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, Response
from history import HistoryStore
from parser import analyze_reports
from report_builder import build_dashboard_html
from jira_client import JiraClient

BASE = Path(__file__).resolve().parent
DB = os.getenv("DATABASE_PATH", str(BASE / "data" / "gct_report_parser.db"))
MAX_FILE_MB = max(0, int(os.getenv("MAX_FILE_SIZE_MB", "0")))
MAX_FILE = MAX_FILE_MB * 1024 * 1024 if MAX_FILE_MB else 0
MAX_REQUEST_MB = max(0, int(os.getenv("MAX_REQUEST_SIZE_MB", "0")))
MAX_REQUEST = MAX_REQUEST_MB * 1024 * 1024 if MAX_REQUEST_MB else None
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = MAX_REQUEST
history = HistoryStore(DB)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/healthz")
def healthz():
    """Lightweight readiness probe for deployment and periodic monitoring."""
    try:
        with history.conn() as connection:
            connection.execute("SELECT 1").fetchone()
        return jsonify({"status": "healthy", "database": "ok"}), 200
    except Exception:
        app.logger.exception("health check failed")
        return jsonify({"status": "unhealthy", "database": "error"}), 503


@app.get("/api/dashboard")
def dashboard():
    return jsonify({
        "generatedAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "buildFingerprint": "Not detected",
        "securityPatch": "Not detected",
        "androidVersion": "Not detected",
        "fingerprints": [],
        "builds": [],
        "uploadedFiles": 0,
        "xmlReportsFound": 0,
        "recognizedReports": 0,
        "reportDiagnostics": [],
        "overall": {
            "totalTests": 0,
            "passed": 0,
            "failed": 0,
            "assumptionFailures": 0,
            "ignored": 0,
            "warnings": 0,
            "blocked": 0,
            "fingerprintMismatch": False,
            "multipleBuilds": False,
            "buildIdentityIncomplete": False,
        },
        "suites": [],
        "incompleteModules": [],
        "failures": [],
    })


@app.get("/api/history")
def history_list():
    return jsonify({"maxRuns": history.MAX_RUNS, "runs": history.list_runs()})


@app.get("/api/history/<run_id>")
def history_run(run_id):
    data = history.get_run(run_id)
    return (jsonify(data), 200) if data else (
        jsonify({"error": "Historical run not found."}), 404
    )


@app.post("/api/analyze")
def analyze():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Upload at least one report ZIP file."}), 400

    paths = []
    try:
        for uploaded in files:
            if not uploaded.filename:
                continue
            if Path(uploaded.filename).suffix.lower() != ".zip":
                return jsonify({
                    "error": f"Only ZIP files are supported: {uploaded.filename}"
                }), 400

            fd, temp_path = tempfile.mkstemp(prefix="gct-report-", suffix=".zip")
            paths.append((uploaded.filename, temp_path))
            written = 0
            with os.fdopen(fd, "wb") as output:
                while True:
                    # Read at most one byte beyond the configured limit so
                    # oversized uploads are rejected without copying the
                    # entire file to the application's temporary directory.
                    chunk_size = 1024 * 1024 if not MAX_FILE else min(1024 * 1024, MAX_FILE - written + 1)
                    chunk = uploaded.stream.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if MAX_FILE and written > MAX_FILE:
                        return jsonify({
                            "error": (
                                f"{uploaded.filename} exceeds the configured "
                                f"{MAX_FILE_MB} MB file limit."
                            )
                        }), 413
                    output.write(chunk)

        if not paths:
            return jsonify({"error": "Upload at least one report ZIP file."}), 400

        data = analyze_reports(paths)
        # Jira is an optional, read-only enrichment step. A Jira outage or bad
        # configuration must never prevent the core report analysis from working.
        try:
            JiraClient().enrich_dashboard(data)
        except Exception:
            app.logger.exception("Jira enrichment failed; returning report without Jira matches")
            data["jiraIntegration"] = {
                "configured": True,
                "status": "error",
                "message": "Jira lookup failed. Report analysis completed without Jira history.",
                "matchedIssues": 0,
            }
            for finding in (data.get("failures") or []) + (data.get("incompleteModules") or []):
                finding["jiraMatches"] = []
                finding["jiraLookupStatus"] = "error"
        history.save(data)
        return jsonify(data)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        app.logger.exception("analysis failed")
        return jsonify({"error": "Analysis failed unexpectedly. Check the application logs for details."}), 500
    finally:
        for _, temp_path in paths:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@app.post("/api/publish")
def publish():
    dashboard_data = request.get_json(silent=True)
    if not isinstance(dashboard_data, dict):
        return jsonify({"error": "Dashboard data is required."}), 400

    html = build_dashboard_html(dashboard_data)
    return Response(
        html.encode("utf-8"),
        mimetype="text/html",
        headers={
            "Content-Disposition": (
                "attachment; filename=gct-certification-dashboard.html"
            ),
            "Cache-Control": "no-store",
        },
    )



@app.errorhandler(413)
def too_large(_):
    return jsonify({
        "error": "Upload is too large for the configured server or proxy limit. Increase that limit and retry."
    }), 413


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8080")),
        debug=os.getenv("DEBUG", "false").lower() == "true",
    )
