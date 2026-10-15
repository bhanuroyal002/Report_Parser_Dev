"""Read-only Jira Cloud search and historical issue enrichment.

Configuration is optional. Without all Jira settings the report parser continues
working normally and the dashboard clearly reports that Jira is not configured.
"""
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


FIELDS = [
    "summary", "description", "status", "resolution", "issuetype",
    "project", "priority", "created", "updated", "resolutiondate", "assignee",
]
MAX_SEARCH_TERMS = 24
MAX_RESULTS_PER_QUERY = 100
MAX_MATCHES_PER_FINDING = 3
TIMEOUT_SECONDS = 12


class JiraConfigurationError(RuntimeError):
    pass


class JiraRequestError(RuntimeError):
    pass


def _clean(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        # Jira Cloud descriptions can be Atlassian Document Format (ADF).
        return " ".join(_clean(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_clean(v) for v in value)
    return re.sub(r"\s+", " ", str(value)).strip()


def _adf_text(value):
    if isinstance(value, dict):
        parts = []
        if value.get("type") == "text" and value.get("text"):
            parts.append(value["text"])
        for child in value.get("content", []) if isinstance(value.get("content"), list) else []:
            parts.append(_adf_text(child))
        return " ".join(part for part in parts if part)
    if isinstance(value, list):
        return " ".join(_adf_text(item) for item in value)
    return ""


def _safe_jql_phrase(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    return value[:180]


def _terms_for_finding(item, kind):
    terms = []
    def add(value):
        value = _safe_jql_phrase(value)
        if len(value) >= 4 and value.lower() not in {t.lower() for t in terms}:
            terms.append(value)

    module = _clean(item.get("module"))
    testcase = _clean(item.get("testCase"))
    details = _clean(item.get("details") or item.get("reason"))
    add(testcase)
    if "#" in testcase:
        class_name, method_name = testcase.split("#", 1)
        add(method_name)
        add(class_name)
    add(module)
    # Error text can be noisy; use a few distinctive phrases rather than the
    # entire stack trace. These remain search terms, not JQL syntax.
    for fragment in re.split(r"[\r\n:;.!]+", details):
        fragment = fragment.strip()
        if len(fragment) >= 8:
            add(fragment[:100])
        if len(terms) >= 5:
            break
    return terms[:5]


def _finding_label(item, kind):
    if kind == "failure":
        return " · ".join(filter(None, [
            _clean(item.get("suite")), _clean(item.get("module")),
            _clean(item.get("testCase")),
        ]))
    return " · ".join(filter(None, [
        _clean(item.get("suite")), _clean(item.get("module")),
    ]))


def _issue_text(issue):
    fields = issue.get("fields") or {}
    description = fields.get("description")
    desc_text = _adf_text(description) if isinstance(description, (dict, list)) else _clean(description)
    return " ".join(filter(None, [
        _clean(fields.get("summary")), desc_text,
        _clean(fields.get("environment")),
    ])).lower()


def _score(issue, item, kind):
    fields = issue.get("fields") or {}
    summary = _clean(fields.get("summary")).lower()
    text = _issue_text(issue)
    module = _clean(item.get("module")).lower()
    testcase = _clean(item.get("testCase")).lower()
    details = _clean(item.get("details") or item.get("reason")).lower()
    score = 0
    match_type = "related"

    if testcase:
        method = testcase.split("#", 1)[-1].strip()
        class_name = testcase.split("#", 1)[0].strip() if "#" in testcase else ""
        if len(method) >= 4 and method in text:
            score += 75
            match_type = "test identity"
        elif len(class_name) >= 5 and class_name in text:
            score += 60
            match_type = "test class"
        elif len(method) >= 5 and method in summary:
            score += 80
            match_type = "test identity"

    if module and len(module) >= 4:
        module_parts = [p for p in re.split(r"[^a-zA-Z0-9]+", module) if len(p) >= 4]
        module_hits = sum(1 for p in module_parts if p in text)
        if module.lower() in text:
            score += 25
        elif module_parts:
            score += min(20, module_hits * 7)

    if details:
        error_parts = [p.lower() for p in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{5,}", details)[:12]]
        error_hits = sum(1 for p in set(error_parts) if p in text)
        score += min(25, error_hits * 5)

    if score >= 70:
        confidence = "high"
    elif score >= 40:
        confidence = "medium"
    else:
        confidence = "low"
    return min(100, score), confidence, match_type


class JiraClient:
    def __init__(self, base_url=None, email=None, api_token=None):
        self.base_url = (base_url or os.getenv("JIRA_BASE_URL", "")).strip().rstrip("/")
        self.email = (email or os.getenv("JIRA_EMAIL", "")).strip()
        self.api_token = api_token or os.getenv("JIRA_API_TOKEN", "")
        self._issue_cache = {}

    @property
    def configured(self):
        return bool(self.base_url and self.email and self.api_token)

    def _request(self, path, payload=None):
        if not self.configured:
            raise JiraConfigurationError("Set JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN to enable Jira lookup.")
        if not re.match(r"^https://[^/]+$", self.base_url, re.I):
            raise JiraConfigurationError("JIRA_BASE_URL must be the HTTPS base URL of your Jira Cloud site.")
        token = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method="POST" if payload is not None else "GET",
            headers={
                "Accept": "application/json",
                "Authorization": "Basic " + token,
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                message = "Jira authentication failed or the account cannot browse the requested issues."
            elif exc.code == 429:
                message = "Jira rate limit reached. Retry the analysis shortly."
            else:
                message = f"Jira API returned HTTP {exc.code}."
            raise JiraRequestError(message) from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise JiraRequestError("Unable to reach Jira Cloud or parse its response.") from exc

    def _search(self, terms):
        phrases = [_safe_jql_phrase(t) for t in terms if _safe_jql_phrase(t)]
        if not phrases:
            return []
        jql = " OR ".join(f'text ~ "{phrase}"' for phrase in phrases)
        result = self._request("/rest/api/3/search/jql", {
            "jql": jql,
            "maxResults": MAX_RESULTS_PER_QUERY,
            "fields": FIELDS,
            "expand": "changelog",
        })
        return result.get("issues", []) if isinstance(result, dict) else []

    def _details(self, issue):
        key = issue.get("key", "")
        if not key:
            return issue
        if key in self._issue_cache:
            return self._issue_cache[key]
        # Search responses may include changelog via expand. If not, request the
        # issue detail endpoint to retrieve a compact recent status history.
        changelog = issue.get("changelog") or {}
        histories = changelog.get("histories") or []
        if not histories:
            encoded_key = urllib.parse.quote(key, safe="")
            try:
                detail = self._request(
                    f"/rest/api/3/issue/{encoded_key}?fields={','.join(FIELDS)}&expand=changelog"
                )
                issue = detail if isinstance(detail, dict) else issue
                changelog = issue.get("changelog") or {}
                histories = changelog.get("histories") or []
            except JiraRequestError:
                # Keep the issue result even if the optional history call fails.
                histories = []

        fields = issue.get("fields") or {}
        status_history = []
        for history in histories:
            for change in history.get("items") or []:
                if change.get("field") == "status":
                    status_history.append({
                        "date": history.get("created", ""),
                        "from": change.get("fromString") or "Unknown",
                        "to": change.get("toString") or "Unknown",
                    })
        status_history.sort(key=lambda row: row.get("date", ""), reverse=True)
        result = {
            "key": key,
            "url": f"{self.base_url}/browse/{urllib.parse.quote(key, safe='')}",
            "summary": _clean(fields.get("summary")) or key,
            "issueType": _clean((fields.get("issuetype") or {}).get("name")),
            "project": _clean((fields.get("project") or {}).get("key")),
            "status": _clean((fields.get("status") or {}).get("name")) or "Unknown",
            "resolution": _clean((fields.get("resolution") or {}).get("name")) or "Unresolved",
            "priority": _clean((fields.get("priority") or {}).get("name")),
            "assignee": _clean((fields.get("assignee") or {}).get("displayName")),
            "created": fields.get("created", ""),
            "updated": fields.get("updated", ""),
            "resolved": fields.get("resolutiondate", ""),
            "statusHistory": status_history[:5],
        }
        self._issue_cache[key] = result
        return result

    def enrich_dashboard(self, dashboard):
        failures = dashboard.get("failures") or []
        incomplete = dashboard.get("incompleteModules") or []
        if not self.configured:
            dashboard["jiraIntegration"] = {
                "configured": False, "status": "not_configured",
                "message": "Jira lookup is optional. Configure the Jira Cloud environment variables to show issue history.",
                "matchedIssues": 0,
            }
            for item in failures + incomplete:
                item["jiraMatches"] = []
                item["jiraLookupStatus"] = "not_configured"
            return dashboard

        findings = [("failure", item) for item in failures] + [("incomplete", item) for item in incomplete]
        if not findings:
            dashboard["jiraIntegration"] = {
                "configured": True, "status": "connected",
                "message": "Jira is configured. No failed test cases or incomplete modules need lookup.",
                "matchedIssues": 0,
            }
            return dashboard

        all_terms = []
        for kind, item in findings:
            all_terms.extend(_terms_for_finding(item, kind))
        unique_terms = []
        seen = set()
        for term in all_terms:
            if term.lower() not in seen:
                seen.add(term.lower())
                unique_terms.append(term)

        # Search in bounded batches to avoid excessively long JQL queries. No
        # project filter is applied: Jira returns issues visible to this account.
        candidates = {}
        try:
            for offset in range(0, len(unique_terms), MAX_SEARCH_TERMS):
                for issue in self._search(unique_terms[offset:offset + MAX_SEARCH_TERMS]):
                    if issue.get("key"):
                        candidates[issue["key"]] = issue
        except (JiraRequestError, JiraConfigurationError) as exc:
            dashboard["jiraIntegration"] = {
                "configured": True, "status": "error", "message": str(exc),
                "matchedIssues": 0,
            }
            for item in failures + incomplete:
                item["jiraMatches"] = []
                item["jiraLookupStatus"] = "error"
            return dashboard

        matched_keys = set()
        for kind, item in findings:
            scores = []
            for issue in candidates.values():
                score, confidence, match_type = _score(issue, item, kind)
                # Do not present a module-only coincidence as a likely defect.
                if score >= 35:
                    scores.append((score, confidence, match_type, issue))
            scores.sort(key=lambda row: (row[0], (row[3].get("fields") or {}).get("updated", "")), reverse=True)
            matches = []
            for score, confidence, match_type, issue in scores[:MAX_MATCHES_PER_FINDING]:
                detail = self._details(issue)
                matches.append({
                    **detail,
                    "matchScore": score,
                    "confidence": confidence,
                    "matchType": match_type,
                })
                matched_keys.add(detail.get("key"))
            item["jiraMatches"] = matches
            item["jiraLookupStatus"] = "matched" if matches else "no_match"

        dashboard["jiraIntegration"] = {
            "configured": True, "status": "connected",
            "message": "Read-only Jira search completed. Only issues visible to the configured Jira account are returned.",
            "matchedIssues": len(matched_keys),
            "checkedFindings": len(findings),
            "candidateIssues": len(candidates),
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }
        return dashboard
