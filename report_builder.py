import html
from datetime import datetime, timezone


def e(value):
    return html.escape("" if value is None else str(value), quote=True)


def text(value):
    return "" if value is None else str(value)


def num(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def maps(value):
    return value if isinstance(value, list) else []


def first_value(root_value, suites, key):
    root = text(root_value)
    if root.strip() and root.lower() != "not detected":
        return root
    for suite in suites:
        value = text(suite.get(key))
        if value.strip() and value.lower() != "not detected":
            return value
    return "Not detected"


def join_values(value):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(v) for v in value if str(v).strip())
    return text(value)


def field(label, value):
    return f"<div class='field'><label>{e(label)}</label><strong>{e(value)}</strong></div>"


def build_dashboard_html(dashboard):
    suites = maps(dashboard.get("suites"))
    failures = maps(dashboard.get("failures"))
    incomplete = maps(dashboard.get("incompleteModules"))
    builds = maps(dashboard.get("builds"))
    overall = dashboard.get("overall") if isinstance(dashboard.get("overall"), dict) else {}

    failed = num(overall.get("failed"))
    fingerprint_mismatch = bool(overall.get("fingerprintMismatch"))
    overall_pass = failed == 0 and not incomplete and not fingerprint_mismatch

    fingerprint = first_value(dashboard.get("buildFingerprint"), suites, "fingerprint")
    patch = first_value(dashboard.get("securityPatch"), suites, "securityPatch")
    android_version = first_value("", suites, "release")
    generated = text(dashboard.get("generatedAt")) or datetime.now(timezone.utc).isoformat()

    css = """
:root{--bg:#f4f7fb;--card:#fff;--ink:#172033;--muted:#667085;--line:#dfe5ef;--navy:#172554;--blue:#2563eb;--cyan:#0891b2;--purple:#7c3aed;--orange:#f97316;--red:#dc2626;--green:#059669;--greenbg:#e9f9f2;--amber:#d97706}
*{box-sizing:border-box}body{margin:0;background:linear-gradient(135deg,#f4f7fb 0%,#eef4ff 48%,#f8f5ff 100%);color:var(--ink);font:14px Arial,Helvetica,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:28px 22px 45px}.header{position:relative;overflow:hidden;background:linear-gradient(120deg,#172554 0%,#1d4ed8 52%,#7c3aed 100%);color:#fff;border-radius:14px;padding:28px 30px;display:flex;justify-content:space-between;gap:20px;align-items:center;box-shadow:0 12px 30px rgba(37,99,235,.16)}
h1{margin:0;font-size:28px;letter-spacing:-.02em}.subtitle{margin-top:7px;color:#dbeafe;font-size:13px}.status{padding:11px 16px;border-radius:999px;font-weight:900;font-size:13px}.status.pass{background:#d1fae5;color:#047857}.status.fail{background:#fee2e2;color:#b91c1c}
.section{background:rgba(255,255,255,.96);border:1px solid var(--line);border-radius:12px;margin-top:16px;padding:22px;box-shadow:0 5px 18px rgba(23,37,84,.05)}.title{font-weight:900;font-size:14px;margin-bottom:16px;padding-left:12px;border-left:4px solid var(--blue);color:var(--navy)}
.summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.field{border:1px solid var(--line);border-top:3px solid var(--cyan);border-radius:9px;padding:13px 14px;background:linear-gradient(180deg,#fff,#f8fbff)}.field:nth-child(2){border-top-color:var(--purple)}.field:nth-child(3){border-top-color:var(--orange)}.field label{display:block;color:var(--muted);font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.06em;margin-bottom:7px}.field strong{font-size:13px;word-break:break-word;line-height:1.45}
.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:9px}table{width:100%;border-collapse:collapse;background:#fff}th{background:linear-gradient(90deg,#eaf2ff,#f2edff);text-align:left;font-size:10px;text-transform:uppercase;color:#475467;padding:12px;white-space:nowrap}td{padding:12px;border-bottom:1px solid #edf0f5}tbody tr:nth-child(even){background:#fafcff}.pass-text{color:var(--green);font-weight:900}.fail-text{color:var(--red);font-weight:900}.inc-text{color:var(--amber);font-weight:900}
.issue{padding:13px 14px;margin:8px 0;border:1px solid #e5eaf2;border-left:4px solid var(--red);border-radius:8px;background:#fffafa}.issue strong{display:block;line-height:1.45}.issue span{display:block;color:var(--muted);margin-top:5px;font-size:12px;line-height:1.45}.empty{color:var(--green);background:var(--greenbg);border:1px solid #b9ead5;padding:13px;border-radius:8px;font-weight:800}.footer{text-align:center;color:var(--muted);font-size:11px;line-height:1.7;margin-top:26px;padding:10px 0}
@media(max-width:700px){.header{display:block}.status{display:inline-block;margin-top:16px}.summary{grid-template-columns:1fr}.wrap{padding:15px 10px}.section{padding:16px}}@media print{body{background:#fff}.wrap{max-width:none;padding:0}.section,.header{break-inside:avoid;box-shadow:none}}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.metric{border:1px solid var(--line);border-top:3px solid var(--blue);border-radius:9px;padding:14px;background:#fff}.metric label{display:block;color:var(--muted);font-size:10px;font-weight:900;letter-spacing:.06em}.metric strong{display:block;font-size:25px;margin:8px 0 4px;font-variant-numeric:tabular-nums}.metric small{color:var(--muted);font-size:11px}.metric.done{border-top-color:var(--green)}.metric.done strong{color:var(--green)}.metric.incomplete{border-top-color:var(--amber)}.metric.incomplete strong{color:var(--amber)}
.charts{display:grid;grid-template-columns:1.2fr 1fr;gap:14px}.chart-panel{border:1px solid var(--line);border-radius:9px;padding:16px;min-width:0}.chart-panel h3{margin:0 0 7px;font-size:15px}.chart-caption{font-size:11px;color:var(--muted);line-height:1.5;margin:0 0 18px}.chart-row{margin:13px 0}.chart-label{display:flex;justify-content:space-between;gap:10px;font-size:11px;margin-bottom:6px}.chart-label strong{overflow-wrap:anywhere}.chart-label span{white-space:nowrap;color:var(--muted)}.track{height:9px;border-radius:99px;background:#edf0f5;overflow:hidden}.track i{display:block;height:100%;background:linear-gradient(90deg,#059669,#6ee7b7);border-radius:99px}.stack{height:18px;display:flex;overflow:hidden;border-radius:5px;background:#edf0f5;margin:20px 0}.seg{height:100%}.seg.passed,.dot.passed{background:#059669}.seg.failed,.dot.failed{background:#dc2626}.seg.assumption,.dot.assumption{background:#d97706}.seg.ignored,.dot.ignored{background:#8792a2}.legend{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;font-size:11px;color:var(--muted)}.legend span{display:flex;align-items:center;gap:6px}.legend b{margin-left:auto;color:var(--ink)}.dot{width:9px;height:9px;border-radius:2px;flex:0 0 9px}
@media(max-width:700px){.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.charts{grid-template-columns:1fr}}@media print{.metrics,.charts{break-inside:avoid}}
"""

    out = [
        "<!doctype html><html lang='en'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>GCT Report Parser · Certification Intelligence</title>",
        f"<style>{css}</style></head><body><div class='wrap'>",
        "<div class='header'><div><h1>GCT Report Parser</h1>"
        "<div class='subtitle'>Certification Intelligence Dashboard · Test execution summary for stakeholder review</div>"
        f"</div><div class='status {'pass' if overall_pass else 'fail'}'>"
        f"{'BUILD MISMATCH' if fingerprint_mismatch else ('PASS' if overall_pass else 'ATTENTION REQUIRED')}</div></div>",
        "<section class='section'><div class='title'>Build Information</div>",
    ]

    if fingerprint_mismatch and builds:
        out.append("<div class='table-wrap'><table><thead><tr><th>Build</th><th>Suite</th><th>Fingerprint</th><th>Android Version</th><th>Security Patch</th></tr></thead><tbody>")
        for i, build in enumerate(builds):
            out.append(
                f"<tr><td><strong>Build {chr(65+i)}</strong></td>"
                f"<td>{e(join_values(build.get('suites')))}</td>"
                f"<td>{e(build.get('fingerprint'))}</td>"
                f"<td>{e(build.get('androidVersion'))}</td>"
                f"<td>{e(build.get('securityPatch'))}</td></tr>"
            )
        out.append("</tbody></table></div>")
    else:
        out.append("<div class='summary'>")
        out.append(field("Build fingerprint", fingerprint))
        out.append(field("Security patch", patch))
        out.append(field("Android version", android_version))
        out.append("</div>")
    out.append("</section>")

    if fingerprint_mismatch:
        out.append(
            "<div class='footer'><strong>GCT Report Parser</strong> · Certification Intelligence<br>"
            "© 2026 CERT_Team · Internal Certification Tool<br>"
            "Build mismatch detected. Test-case and module metrics were not included because the uploaded reports belong to different builds.</div>"
            "</div></body></html>"
        )
        return "".join(out)

    module_total = sum(num(suite.get("modules")) for suite in suites)
    module_done = sum(num(suite.get("completedModules")) for suite in suites)
    module_incomplete = max(0, module_total - module_done)
    completion_rate = round(module_done / module_total * 100) if module_total else 0
    out.append("<section class='section'><div class='title'>Suite completion overview</div><div class='metrics'>")
    metric_values = [("TOTAL MODULES", module_total, "Across all detected suites", "total"), ("COMPLETED", module_done, (str(completion_rate) + "% completion") if module_total else "No module data", "done"), ("INCOMPLETE", module_incomplete, "Modules not yet completed", "incomplete"), ("SUITES", len(suites), "Detected certification suites", "suites")]
    for label, value, caption, kind in metric_values:
        out.append("<div class='metric " + e(kind) + "'><label>" + e(label) + "</label><strong>" + format(value, ',') + "</strong><small>" + e(caption) + "</small></div>")
    out.append("</div></section>")
    outcomes = [("Passed", num(overall.get("passed")), "passed"), ("Failed", num(overall.get("failed")), "failed"), ("Assumption failures", num(overall.get("assumptionFailures")), "assumption"), ("Ignored", num(overall.get("ignored")), "ignored")]
    outcome_total = sum(value for _, value, _ in outcomes)
    out.append("<section class='section'><div class='title'>Visual execution charts</div><div class='charts'><div class='chart-panel'><h3>Suite completion</h3><p class='chart-caption'>Completed modules compared with total modules in each suite.</p>")
    if not suites:
        out.append("<div class='empty'>No suite data available.</div>")
    for suite in suites:
        total = num(suite.get("modules"))
        done = num(suite.get("completedModules"))
        pct = max(0, min(100, done / total * 100)) if total else 0
        out.append("<div class='chart-row'><div class='chart-label'><strong>" + e(suite.get("name")) + "</strong><span>" + format(done, ',') + " / " + format(total, ',') + " · " + str(round(pct)) + "%</span></div><div class='track' role='img' aria-label='Module completion'><i style='width:" + format(pct, '.3f') + "%'></i></div></div>")
    out.append("</div><div class='chart-panel'><h3>Test outcome distribution</h3><p class='chart-caption'>" + format(outcome_total, ',') + " passed, failed, assumption-failure and ignored outcomes combined.</p><div class='stack' role='img' aria-label='Test outcome distribution'>")
    for label, value, kind in outcomes:
        width = value / outcome_total * 100 if outcome_total else 0
        if width > 0:
            out.append("<span class='seg " + kind + "' style='width:" + format(width, '.3f') + "%'></span>")
    out.append("</div><div class='legend'>")
    for label, value, kind in outcomes:
        out.append("<span><i class='dot " + kind + "'></i>" + e(label) + "<b>" + format(value, ',') + "</b></span>")
    out.append("</div></div></div></section>")
    out.append("<section class='section'><div class='title'>Suite summary</div><div class='table-wrap'><table>"
               "<thead><tr><th>Suite</th><th>Mods</th><th>Done</th><th>Incomplete Modules</th><th>Passed</th><th>Failed</th>"
               "<th>Assumption Failure</th><th>Ignored</th><th>Warnings</th><th>Total Tests</th></tr></thead><tbody>")

    for suite in suites:
        mods = num(suite.get("modules"))
        done = num(suite.get("completedModules"))
        inc = max(0, mods - done)
        failed_count = num(suite.get("failed"))
        out.append(
            f"<tr><td><strong>{e(suite.get('name'))}</strong></td><td>{mods}</td><td>{done}</td>"
            f"<td class='{'pass-text' if inc == 0 else 'inc-text'}'>{inc}</td>"
            f"<td class='pass-text'>{num(suite.get('passed'))}</td>"
            f"<td class='{'pass-text' if failed_count == 0 else 'fail-text'}'>{failed_count}</td>"
            f"<td>{num(suite.get('assumptionFailures'))}</td><td>{num(suite.get('ignored'))}</td>"
            f"<td>{num(suite.get('warnings'))}</td><td>{num(suite.get('testCases'))}</td></tr>"
        )
    out.append("</tbody></table></div></section>")

    out.append("<section class='section'><div class='title'>Incomplete modules</div>")
    if not incomplete:
        out.append("<div class='empty'>No incomplete modules.</div>")
    else:
        for item in incomplete:
            out.append(
                f"<div class='issue'><strong>{e(item.get('suite'))} {e(item.get('module'))}</strong>"
                f"<span>{e(item.get('reason') or 'Module incomplete')}</span>"
            )
            out.append("</div>")
    out.append("</section>")

    out.append("<section class='section'><div class='title'>Failed test cases</div>")
    if not failures:
        out.append("<div class='empty'>No failed test cases.</div>")
    else:
        for failure in failures:
            out.append(
                f"<div class='issue'><strong> - {e(failure.get('suite'))} "
                f"{e(failure.get('module'))} :: {e(failure.get('testCase'))}</strong>"
                f"<span>{e(failure.get('details') or 'No failure details recorded.')}</span>"
            )
            out.append("</div>")
    out.append("</section>")

    out.append(
        f"<div class='footer'><div>Generated {e(generated)} · GCT Report Parser · Certification Intelligence</div>"
        "<div>© 2026 CERT_Team · Internal Certification Tool</div></div></div></body></html>"
    )
    return "".join(out)
