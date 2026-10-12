import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from werkzeug.utils import secure_filename

from flask import Flask, after_this_request, jsonify, render_template, request, Response, send_file
from history import HistoryStore
from parser import analyze_reports
from report_builder import build_dashboard_html

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



@app.post("/api/apa-upload")
def apa_upload():
    """Package uploaded ZIP reports with suite-based filenames."""
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Upload at least one report ZIP file."}), 400

    temp_paths = []
    output_path = None
    try:
        parsed_files = []
        for uploaded in files:
            if not uploaded.filename:
                continue
            if Path(uploaded.filename).suffix.lower() != ".zip":
                return jsonify({"error": f"Only ZIP files are supported: {uploaded.filename}"}), 400
            fd, temp_path = tempfile.mkstemp(prefix="gct-apa-source-", suffix=".zip")
            temp_paths.append(temp_path)
            written = 0
            with os.fdopen(fd, "wb") as output:
                while True:
                    chunk_size = 1024 * 1024 if not MAX_FILE else min(1024 * 1024, MAX_FILE - written + 1)
                    chunk = uploaded.stream.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if MAX_FILE and written > MAX_FILE:
                        return jsonify({"error": f"{uploaded.filename} exceeds the configured {MAX_FILE_MB} MB file limit."}), 413
                    output.write(chunk)
            parsed_files.append((uploaded.filename, temp_path))

        if not parsed_files:
            return jsonify({"error": "Upload at least one report ZIP file."}), 400

        named = []
        project_name = ""
        sw_version = ""
        for original_name, path in parsed_files:
            detected = analyze_reports([(original_name, path)])
            suite_names = list(dict.fromkeys(str(item.get("name") or "").strip() for item in detected.get("suites", []) if str(item.get("name") or "").strip()))
            suite = "_".join(suite_names) if suite_names else "UnknownSuite"
            suite = secure_filename(suite.replace(" ", "_")) or "UnknownSuite"
            named.append((suite, path))

            builds = detected.get("builds") or []
            fingerprint = str((builds[0].get("fingerprint") if builds else detected.get("buildFingerprint")) or "").strip()
            if fingerprint and fingerprint != "Not detected" and not detected.get("overall", {}).get("fingerprintMismatch"):
                parts = fingerprint.split("/")
                if not project_name and parts:
                    project_name = secure_filename(parts[0].replace(" ", "_"))
                if len(parts) >= 2:
                    version_part = parts[-1].split(":", 1)[0]
                    if version_part and any(ch.isdigit() for ch in version_part):
                        sw_version = secure_filename(version_part.replace(" ", "_"))

        project_name = project_name or "UnknownProject"
        sw_version = sw_version or "UnknownSWVersion"

        totals = Counter(suite for suite, _ in named)
        seen = Counter()
        output_names = []
        for suite, path in named:
            seen[suite] += 1
            filename = f"{suite}_report.zip" if totals[suite] == 1 else f"{suite}_report{seen[suite]}.zip"
            output_names.append((filename, path))

        fd, output_path = tempfile.mkstemp(prefix="gct-apa-upload-", suffix=".zip")
        os.close(fd)
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as package:
            for archive_name, path in output_names:
                package.write(path, arcname=archive_name)

        @after_this_request
        def remove_package(response):
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return response

        return send_file(output_path, mimetype="application/zip", as_attachment=True, download_name=f"{project_name}_{sw_version}_APA_reports.zip", conditional=True)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("APA report packaging failed")
        return jsonify({"error": "Unable to package the uploaded reports. Check the application logs."}), 500
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


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
