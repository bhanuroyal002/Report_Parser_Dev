import hashlib
import io
import os
import zipfile
from collections import OrderedDict
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

MAX_DEPTH = int(os.getenv("MAX_ZIP_DEPTH", "20"))


def first(*values):
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def num(value, default=0):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def normalize_suite(name, plan):
    value = first(plan, name).upper().strip().replace("_", "-").replace(" ", "-")
    if value in {"VERIFIER", "CTSVERIFIER", "CTS-VERIFIER"}:
        return "CTS-VERIFIER"
    if value == "CTS-ON-GSI":
        return "CTS-ON-GSI"
    return value


def normalize_fingerprint(value):
    value = first(value)
    return "" if not value or value.lower() == "not detected" else value.lower()


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def attr(element, name, default=""):
    return first(element.attrib.get(name), default)


def parse_tradefed_xml(data, source):
    # iterparse keeps memory bounded much better than building a full DOM for
    # very large Tradefed test_result.xml files.
    stream = io.BytesIO(data)
    context = ET.iterparse(stream, events=("start", "end"))

    root_seen = False
    suite_name = suite_plan = suite_version = suite_build = ""
    host_name = os_name = os_version = start = end = ""
    fingerprint = patch = release = sdk = abis = build_id = build_type = ""

    summary = {
        "passed": 0, "failed": 0, "assumptionFailures": 0,
        "ignored": 0, "warnings": 0, "modulesDone": 0, "modulesTotal": 0
    }

    modules = []
    failures = []
    tests = []
    current_module = None
    current_testcase = ""
    current_test = None
    failure_message = ""
    stack_trace = ""
    in_failure = False
    in_stack_trace = False

    for event, element in context:
        name = local_name(element.tag)

        if event == "start":
            if name == "Result" and not root_seen:
                root_seen = True
                suite_name = attr(element, "suite_name")
                suite_plan = attr(element, "suite_plan")
                suite_version = attr(element, "suite_version")
                suite_build = attr(element, "suite_build_number")
                host_name = attr(element, "host_name")
                os_name = attr(element, "os_name")
                os_version = attr(element, "os_version")
                start = first(element.attrib.get("start_display"), element.attrib.get("start"))
                end = first(element.attrib.get("end_display"), element.attrib.get("end"))
                continue

            if not root_seen:
                continue

            if name == "Summary":
                summary["passed"] = num(element.attrib.get("pass"), summary["passed"])
                summary["failed"] = num(element.attrib.get("failed"), summary["failed"])
                summary["assumptionFailures"] = num(
                    element.attrib.get("assumption_failure"),
                    num(element.attrib.get("assumption_failures"), summary["assumptionFailures"])
                )
                summary["ignored"] = num(element.attrib.get("ignored"), summary["ignored"])
                summary["warnings"] = num(
                    element.attrib.get("warning"),
                    num(element.attrib.get("warnings"), summary["warnings"])
                )
                summary["modulesDone"] = num(element.attrib.get("modules_done"), summary["modulesDone"])
                summary["modulesTotal"] = num(element.attrib.get("modules_total"), summary["modulesTotal"])

            elif name == "Build":
                fingerprint = attr(element, "build_fingerprint", fingerprint)
                patch = attr(element, "build_version_security_patch", patch)
                release = attr(element, "build_version_release", release)
                sdk = attr(element, "build_version_sdk", sdk)
                abis = attr(element, "build_abis", abis)
                build_id = first(element.attrib.get("build_id"), element.attrib.get("build_version_incremental"), build_id)
                build_type = attr(element, "build_type", build_type)

            elif name == "Module":
                current_module = {
                    "name": first(element.attrib.get("name"), "Unknown Module"),
                    "abi": first(element.attrib.get("abi")),
                    "passed": num(element.attrib.get("pass"), -1),
                    "failed": 0,
                    "assumptionFailures": 0,
                    "ignored": 0,
                    "totalTests": 0,
                    "done": first(element.attrib.get("done"), "false").lower() == "true",
                }
                current_testcase = ""

            elif name == "TestCase" and current_module is not None:
                current_testcase = first(element.attrib.get("name"))

            elif name == "Test" and current_module is not None:
                result = first(element.attrib.get("result")).lower().replace("-", "_")
                test_name = first(element.attrib.get("name"), "Unknown Test")
                current_test = {
                    "suite": normalize_suite(suite_name, suite_plan),
                    "module": current_module["name"],
                    "abi": current_module["abi"],
                    "testCase": current_testcase,
                    "name": test_name,
                    "result": result,
                    "details": "",
                    "key": hashlib.sha256(
                        ("|".join([
                            normalize_suite(suite_name, suite_plan),
                            current_module["abi"],
                            current_module["name"],
                            current_testcase,
                            test_name,
                        ])).lower().encode()
                    ).hexdigest(),
                }
                current_module["totalTests"] += 1
                failure_message = ""
                stack_trace = ""

            elif name == "Failure" and current_test is not None:
                in_failure = True
                failure_message = first(element.attrib.get("message"))

            elif name == "StackTrace" and in_failure and current_test is not None:
                in_stack_trace = True
                stack_trace = ""

        else:
            if name == "StackTrace" and in_stack_trace:
                in_stack_trace = False
                if not failure_message:
                    failure_message = (element.text or "").strip() or stack_trace.strip()

            elif name == "Failure" and in_failure:
                in_failure = False
                if not failure_message:
                    failure_message = stack_trace.strip()

            elif name == "Test" and current_test is not None:
                current_test["details"] = first(failure_message, "Test failed")
                result = current_test["result"]
                if result == "pass":
                    pass
                elif result == "fail":
                    current_module["failed"] += 1
                    failures.append({
                        "suite": current_test["suite"],
                        "module": (current_test["abi"] + " " + current_test["module"]).strip(),
                        "testCase": current_test["testCase"] + "#" + current_test["name"],
                        "details": current_test["details"],
                    })
                elif result in {"assumption_failure", "assumption-failures"}:
                    current_module["assumptionFailures"] += 1
                elif result in {"ignored", "not_executed"}:
                    current_module["ignored"] += 1
                tests.append(current_test)
                current_test = None

            elif name == "TestCase":
                current_testcase = ""

            elif name == "Module" and current_module is not None:
                module = current_module
                if module["passed"] < 0:
                    module["passed"] = max(0, module["totalTests"] - module["failed"])
                if not module["done"]:
                    failures_reason = {
                        "suite": normalize_suite(suite_name, suite_plan),
                        "module": (module["abi"] + " " + module["name"]).strip(),
                        "reason": "Module is marked done=false in Tradefed result",
                    }
                else:
                    failures_reason = None
                if failures_reason:
                    modules.append({**module})
                    # incomplete entries are built below from module state.
                else:
                    modules.append({**module})
                current_module = None

            elif name == "Result" and root_seen:
                root_seen = False

            # Free completed XML elements to keep memory usage bounded.
            element.clear()

    suite = normalize_suite(suite_name, suite_plan)
    if not suite:
        return None

    # Summary values are authoritative when present. Older reports may omit
    # some counters, so derive missing values from module/test records.
    if summary["assumptionFailures"] == 0:
        summary["assumptionFailures"] = sum(m["assumptionFailures"] for m in modules)
    if summary["ignored"] == 0:
        summary["ignored"] = sum(m["ignored"] for m in modules)
    if summary["modulesTotal"] == 0:
        summary["modulesTotal"] = len(modules)
    if summary["modulesDone"] == 0 and modules:
        summary["modulesDone"] = sum(1 for m in modules if m["done"])
    if summary["passed"] == 0 and summary["failed"] == 0 and modules:
        summary["passed"] = sum(m["passed"] for m in modules)
        summary["failed"] = sum(m["failed"] for m in modules)

    incomplete = [{
        "suite": suite,
        "module": (m["abi"] + " " + m["name"]).strip(),
        "failed": m["failed"],
        "reason": "Module is marked done=false in Tradefed result",
    } for m in modules if not m["done"]]

    return {
        "suite": suite,
        "plan": first(suite_plan, suite),
        "version": suite_version,
        "buildNumber": suite_build,
        "hostInfo": (
            f"Result/@start {first(host_name, 'unknown')} "
            f"({first(os_name, 'unknown')} - {first(os_version, 'unknown')})"
            if any((host_name, os_name, os_version)) else "Not detected"
        ),
        "start": start,
        "end": end,
        "passed": summary["passed"],
        "failed": summary["failed"],
        "assumptionFailures": summary["assumptionFailures"],
        "ignored": summary["ignored"],
        "warnings": summary["warnings"],
        "modulesDone": summary["modulesDone"],
        "modulesTotal": summary["modulesTotal"],
        "testCases": summary["passed"] + summary["failed"] + summary["assumptionFailures"] + summary["ignored"],
        "fingerprint": first(fingerprint, "Not detected"),
        "securityPatch": first(patch, "Not detected"),
        "release": first(release, "Not detected"),
        "sdk": first(sdk, "Not detected"),
        "abis": first(abis, "Not detected"),
        "buildId": first(build_id, "Not detected"),
        "buildType": first(build_type, "Not detected"),
        "status": "COMPLETED" if summary["modulesTotal"] > 0 and summary["modulesDone"] >= summary["modulesTotal"] else "INCOMPLETE",
        "moduleDetails": modules,
        "failures": failures,
        "incomplete": incomplete,
        "tests": tests,
        "moduleDoneStates": {
            (m["abi"] + "|" + m["name"]).lower(): m["done"] for m in modules
        },
        "source": source,
    }


def scan_archive(archive, source, depth, seen_xml, seen_zip):
    if depth > MAX_DEPTH:
        return [], 0, [f"{source}: maximum nested ZIP depth reached ({MAX_DEPTH})."]

    reports = []
    xml_found = 0
    errors = []

    for entry in archive.infolist():
        if entry.is_dir():
            continue
        name = entry.filename
        lower = name.lower()
        is_result_xml = lower.endswith("test_result.xml")
        is_nested_zip = lower.endswith(".zip")
        if not (is_result_xml or is_nested_zip):
            continue

        try:
            payload = archive.read(entry)
        except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
            errors.append(f"{source}!{name}: unable to read ZIP entry ({exc})")
            continue

        if is_result_xml:
            xml_found += 1
            digest = hashlib.sha256(payload).hexdigest()
            if digest not in seen_xml:
                seen_xml.add(digest)
                try:
                    report = parse_tradefed_xml(payload, f"{source}!{name}")
                    if report is not None:
                        reports.append(report)
                    else:
                        errors.append(f"{source}!{name}: suite name/plan was not detected.")
                except (ET.ParseError, UnicodeError, ValueError) as exc:
                    errors.append(f"{source}!{name}: XML parse error ({exc})")

        if is_nested_zip:
            digest = hashlib.sha256(payload).hexdigest()
            if digest in seen_zip:
                continue
            seen_zip.add(digest)
            try:
                with zipfile.ZipFile(io.BytesIO(payload)) as nested_archive:
                    nested, found, nested_errors = scan_archive(
                        nested_archive, f"{source}!{name}", depth + 1, seen_xml, seen_zip
                    )
            except zipfile.BadZipFile as exc:
                errors.append(f"{source}!{name}: invalid nested ZIP ({exc})")
                continue
            reports.extend(nested)
            xml_found += found
            errors.extend(nested_errors)

    return reports, xml_found, errors


def scan_bytes(data, source, depth, seen_xml, seen_zip):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return scan_archive(archive, source, depth, seen_xml, seen_zip)
    except zipfile.BadZipFile as exc:
        return [], 0, [f"{source}: invalid ZIP ({exc})"]


def scan(path, name, seen_xml, seen_zip):
    # Open the outer ZIP directly from disk instead of loading the entire
    # archive into RAM first. This avoids an extra full-file memory copy for
    # large certification reports; nested ZIPs are read only when encountered.
    try:
        with zipfile.ZipFile(path) as archive:
            return scan_archive(archive, name, 0, seen_xml, seen_zip)
    except zipfile.BadZipFile as exc:
        return [], 0, [f"{name}: invalid ZIP ({exc})"]
    except OSError as exc:
        return [], 0, [f"{name}: {exc}"]

def merge_reports(reports):
    if not reports:
        return {}


    if len(reports) == 1:
        report = reports[0]
        return {
            "name": report["suite"],
            "plan": report["plan"],
            "version": report["version"],
            "buildNumber": report["buildNumber"],
            "hostInfo": report["hostInfo"],
            "start": report["start"],
            "end": report["end"],
            "passed": report["passed"],
            "failed": report["failed"],
            "assumptionFailures": report["assumptionFailures"],
            "ignored": report["ignored"],
            "warnings": report["warnings"],
            "modules": report["modulesTotal"],
            "completedModules": report["modulesDone"],
            "testCases": report["testCases"],
            "status": report["status"],
            "fingerprint": report["fingerprint"],
            "securityPatch": report["securityPatch"],
            "release": report["release"],
            "sdk": report["sdk"],
            "abis": report["abis"],
            "buildId": report["buildId"],
            "buildType": report["buildType"],
            "moduleDetails": report["moduleDetails"],
            "_failures": report["failures"],
            "_incomplete": report["incomplete"],
        }

    test_results = OrderedDict()
    module_info = OrderedDict()

    plan = version = build_number = host_info = start = end = ""
    fingerprint_value = patch = release = sdk = abis = build_id = build_type = ""

    for report in reports:
        plan = first(plan, report["plan"])
        version = first(version, report["version"])
        build_number = first(build_number, report["buildNumber"])
        host_info = first(host_info, report["hostInfo"])
        start = first(start, report["start"])
        end = first(end, report["end"])
        fingerprint_value = first(fingerprint_value, None if report["fingerprint"] == "Not detected" else report["fingerprint"])
        patch = first(patch, None if report["securityPatch"] == "Not detected" else report["securityPatch"])
        release = first(release, report["release"])
        sdk = first(sdk, report["sdk"])
        abis = first(abis, report["abis"])
        build_id = first(build_id, report["buildId"])
        build_type = first(build_type, report["buildType"])

        for test in report["tests"]:
            old = test_results.get(test["key"])
            if old is None or old["result"] != "pass":
                test_results[test["key"]] = test

        for module in report["moduleDetails"]:
            key = (module["abi"] + "|" + module["name"]).lower()
            old = module_info.get(key)
            if old is None or (
                (module["done"] and not old["done"])
                or (module["done"] == old["done"] and module["totalTests"] >= old["totalTests"])
            ):
                module_info[key] = dict(module)

    modules = list(module_info.values())
    counts = {
        (m["abi"] + "|" + m["name"]).lower(): {
            "passed": 0, "failed": 0, "assumptionFailures": 0, "ignored": 0, "totalTests": 0
        } for m in modules
    }
    failures = []

    for test in test_results.values():
        key = (test["abi"] + "|" + test["module"]).lower()
        counts.setdefault(key, {"passed": 0, "failed": 0, "assumptionFailures": 0, "ignored": 0, "totalTests": 0})
        counts[key]["totalTests"] += 1
        result = test["result"]
        if result == "pass":
            counts[key]["passed"] += 1
        elif result == "fail":
            counts[key]["failed"] += 1
            failures.append({
                "suite": test["suite"],
                "module": (test["abi"] + " " + test["module"]).strip(),
                "testCase": test["testCase"] + "#" + test["name"],
                "details": first(test["details"], "Test failed"),
            })
        elif result == "assumption_failure":
            counts[key]["assumptionFailures"] += 1
        elif result in {"ignored", "not_executed"}:
            counts[key]["ignored"] += 1

    module_rows = []
    incomplete = []
    for key, module in module_info.items():
        row = dict(module)
        row.update(counts.get(key, {}))
        module_rows.append(row)
        if not row["done"]:
            incomplete.append({
                "suite": reports[0]["suite"],
                "module": (row["abi"] + " " + row["name"]).strip(),
                "failed": row["failed"],
                "reason": "Module is marked done=false in Tradefed result",
            })

    if test_results:
        passed = sum(t["result"] == "pass" for t in test_results.values())
        failed = sum(t["result"] == "fail" for t in test_results.values())
        assumption = sum(t["result"] == "assumption_failure" for t in test_results.values())
        ignored = sum(t["result"] in {"ignored", "not_executed"} for t in test_results.values())
    else:
        passed = sum(r["passed"] for r in reports)
        failed = sum(r["failed"] for r in reports)
        assumption = sum(r["assumptionFailures"] for r in reports)
        ignored = sum(r["ignored"] for r in reports)

    modules_total = len(module_rows)
    modules_done = sum(1 for m in module_rows if m["done"])

    return {
        "name": reports[0]["suite"],
        "plan": plan,
        "version": version,
        "buildNumber": build_number,
        "hostInfo": host_info,
        "start": start,
        "end": end,
        "passed": passed,
        "failed": failed,
        "assumptionFailures": assumption,
        "ignored": ignored,
        "warnings": max((r["warnings"] for r in reports), default=0),
        "modules": modules_total,
        "completedModules": modules_done,
        "testCases": passed + failed + assumption + ignored,
        "status": "COMPLETED" if modules_total > 0 and modules_done >= modules_total else "INCOMPLETE",
        "fingerprint": first(fingerprint_value, "Not detected"),
        "securityPatch": first(patch, "Not detected"),
        "release": first(release, "Not detected"),
        "sdk": first(sdk, "Not detected"),
        "abis": first(abis, "Not detected"),
        "buildId": first(build_id, "Not detected"),
        "buildType": first(build_type, "Not detected"),
        "moduleDetails": module_rows,
        "_failures": failures,
        "_incomplete": incomplete,
    }


def analyze_reports(files):
    all_reports = []
    diagnostics = []
    seen_xml = set()
    seen_zip = set()

    for filename, path in files:
        reports, xml_found, errors = scan(path, filename, seen_xml, seen_zip)
        all_reports.extend(reports)
        diagnostics.append({
            "file": filename,
            "xmlFilesFound": xml_found,
            "recognizedReports": len(reports),
            "errors": errors,
        })

    if not all_reports:
        raise ValueError("No recognized Tradefed test_result.xml reports were found in the uploaded ZIP files.")

    reports_by_build = OrderedDict()
    known_fingerprints = OrderedDict()
    unknown_present = False

    for report in all_reports:
        fp_key = normalize_fingerprint(report["fingerprint"])
        if fp_key:
            known_fingerprints[fp_key] = report["fingerprint"]
        else:
            unknown_present = True
        reports_by_build.setdefault(fp_key or "not detected", []).append(report)

    multiple_builds = len(known_fingerprints) > 1
    build_identity_incomplete = unknown_present and bool(known_fingerprints)
    fingerprint_mismatch = multiple_builds or build_identity_incomplete

    # Merge each suite within each build. Even on a mismatch we retain suite
    # rows in the saved dashboard, while overall test metrics are suppressed.
    suites = []
    incomplete = []
    failures = []
    for build_reports in reports_by_build.values():
        by_suite = OrderedDict()
        for report in build_reports:
            by_suite.setdefault(report["suite"], []).append(report)
        for group in by_suite.values():
            merged = merge_reports(group)
            incomplete.extend(merged.pop("_incomplete", []))
            failures.extend(merged.pop("_failures", []))
            suites.append(merged)

    builds = []
    for fp_key, build_reports in reports_by_build.items():
        build = {
            "fingerprint": build_reports[0]["fingerprint"],
            "securityPatch": "Not detected",
            "androidVersion": "Not detected",
            "buildId": "Not detected",
            "buildType": "Not detected",
            "sdk": "Not detected",
            "abis": "Not detected",
            "suites": [],
        }
        for report in build_reports:
            for field, target in (
                ("securityPatch", "securityPatch"), ("release", "androidVersion"),
                ("buildId", "buildId"), ("buildType", "buildType"),
                ("sdk", "sdk"), ("abis", "abis")
            ):
                value = report.get(field, "")
                if value and value.lower() != "not detected":
                    build[target] = value
            if report["suite"] and report["suite"] not in build["suites"]:
                build["suites"].append(report["suite"])
        builds.append(build)

    if len(known_fingerprints) == 1 and not build_identity_incomplete:
        first_known = next((r for r in all_reports if normalize_fingerprint(r["fingerprint"])), None)
        dashboard_fp = first_known["fingerprint"] if first_known else "Not detected"
        dashboard_patch = first_known["securityPatch"] if first_known else "Not detected"
    elif multiple_builds:
        dashboard_fp = "MULTIPLE BUILDS DETECTED"
        dashboard_patch = "Not detected"
    elif build_identity_incomplete:
        dashboard_fp = "BUILD IDENTITY INCOMPLETE"
        dashboard_patch = "Not detected"
    else:
        dashboard_fp = "Not detected"
        dashboard_patch = "Not detected"

    total = sum(int(x.get("testCases", 0)) for x in suites)
    passed = sum(int(x.get("passed", 0)) for x in suites)
    failed = sum(int(x.get("failed", 0)) for x in suites)
    assumption = sum(int(x.get("assumptionFailures", 0)) for x in suites)
    ignored = sum(int(x.get("ignored", 0)) for x in suites)
    warnings = sum(int(x.get("warnings", 0)) for x in suites)

    overall = {
        "totalTests": 0 if fingerprint_mismatch else total,
        "passed": 0 if fingerprint_mismatch else passed,
        "failed": 0 if fingerprint_mismatch else failed,
        "assumptionFailures": 0 if fingerprint_mismatch else assumption,
        "ignored": 0 if fingerprint_mismatch else ignored,
        "warnings": 0 if fingerprint_mismatch else warnings,
        "blocked": 0 if fingerprint_mismatch else len(incomplete),
        "fingerprintMismatch": fingerprint_mismatch,
        "multipleBuilds": multiple_builds,
        "buildIdentityIncomplete": build_identity_incomplete,
    }

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "buildFingerprint": dashboard_fp,
        "securityPatch": dashboard_patch,
        "androidVersion": builds[0].get("androidVersion", "Not detected") if builds else "Not detected",
        "fingerprints": list(known_fingerprints.values()),
        "builds": builds,
        "uploadedFiles": len(files),
        "xmlReportsFound": sum(d["xmlFilesFound"] for d in diagnostics),
        "recognizedReports": len(all_reports),
        "reportDiagnostics": diagnostics,
        "overall": overall,
        "suites": suites,
        "incompleteModules": [] if fingerprint_mismatch else incomplete,
        "failures": [] if fingerprint_mismatch else failures,
    }
