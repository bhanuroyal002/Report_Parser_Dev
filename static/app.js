const state={data:null,files:[]};
const $=id=>document.getElementById(id);
const format=n=>Number(n||0).toLocaleString("en-IN");
const formatBytes=b=>{const n=Number(b||0);if(n<1024)return n+' B';if(n<1048576)return (n/1024).toFixed(1)+' KB';if(n<1073741824)return (n/1048576).toFixed(1)+' MB';return (n/1073741824).toFixed(2)+' GB'};
function setProgress(percent,title,detail,indeterminate=false){const box=$("analysisProgress");box.classList.remove("hidden");$("progressTitle").textContent=title;$("progressDetail").textContent=detail;$("progressPercent").textContent=indeterminate?"":percent+"%";$("progressBar").style.width=indeterminate?"35%":Math.max(0,Math.min(100,percent))+"%";$("progressTrack").classList.toggle("indeterminate",indeterminate)}
function hideProgress(){clearInterval(state.progressTimer);state.progressTimer=null;$("analysisProgress").classList.add("hidden");$("progressTrack").classList.remove("indeterminate")}
const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function jiraMatchesMarkup(item){
  const matches=Array.isArray(item.jiraMatches)?item.jiraMatches:[];
  if(matches.length){
    return '<div class="jira-matches"><strong>Jira history</strong>'+matches.map(function(issue){
      const history=(issue.statusHistory||[]).slice(0,3).map(function(h){return '<li>'+esc(h.from)+' → '+esc(h.to)+' <small>'+esc(h.date||'')+'</small></li>';}).join('');
      return '<div class="jira-match"><a href="'+esc(issue.url)+'" target="_blank" rel="noopener noreferrer"><strong>'+esc(issue.key)+'</strong></a> '+esc(issue.summary||'')+'<div class="jira-meta"><span>'+esc(issue.status||'Unknown')+'</span><span>'+esc(issue.resolution||'Unresolved')+'</span><span>'+esc(issue.confidence||'')+' confidence</span></div>'+(issue.updated?'<small>Updated '+esc(issue.updated)+'</small>':'')+(history?'<details><summary>Status history</summary><ul>'+history+'</ul></details>':'')+'</div>';
    }).join('')+'</div>';
  }
  if(item.jiraLookupStatus==='error') return '<div class="jira-empty">Jira lookup failed; report analysis is still available.</div>';
  if(!item.jiraLookupStatus) return '<div class="jira-empty">Jira history was not stored for this analysis run.</div>';
  if(item.jiraLookupStatus==='no_match') return '<div class="jira-empty">No matching Jira issue found.</div>';
  const jira=state.data&&state.data.jiraIntegration;
  if(!jira||!jira.configured) return '<div class="jira-empty">Jira lookup not configured.</div>';
  return '<div class="jira-empty">No matching Jira issue found.</div>';
}
function renderJiraStatus(){
  const target=$("jiraStatus");if(!target)return;
  const jira=state.data&&state.data.jiraIntegration||{};
  target.innerHTML='<strong>Jira history · '+esc(jira.status||'not configured')+'</strong><p>'+esc(jira.message||'Configure Jira Cloud credentials on the server to look up existing issues.')+(jira.checkedFindings!==undefined?' Checked '+format(jira.checkedFindings)+' findings · '+format(jira.matchedIssues||0)+' unique matching issues.':'')+'</p>';
  target.classList.toggle('jira-status-error',jira.status==='error');
}
function renderFiles(){
  const total=state.files.reduce((sum,f)=>sum+f.size,0);
  $("selectedFiles").innerHTML=state.files.map(f=>`<span class="file-chip">${esc(f.name)} <small>${formatBytes(f.size)}</small></span>`).join("");
  if(state.files.length)$("statusMessage").textContent=`${state.files.length} ZIP file${state.files.length===1?"":"s"} selected · ${formatBytes(total)} total`;
  $("analyzeBtn").disabled=!state.files.length;
  $("clearBtn").disabled=!state.files.length;
}
function render(){
  const d=state.data;if(!d)return;
  const o=d.overall||{},s=d.suites||[],inc=d.incompleteModules||[],fail=d.failures||[];
  const builds=d.builds||[];
  const fingerprintMismatch=Boolean(o.fingerprintMismatch);
  const primaryBuild=builds[0]||{};
  $("buildFingerprint").textContent=fingerprintMismatch?"MULTIPLE BUILDS DETECTED":(primaryBuild.fingerprint||d.buildFingerprint||"Not detected");
  $("securityPatch").textContent=fingerprintMismatch?"MULTIPLE":(primaryBuild.securityPatch||d.securityPatch||"Not detected");
  $("androidVersion").textContent=fingerprintMismatch?"MULTIPLE":(primaryBuild.androidVersion||d.androidVersion||"Not detected");
  const suiteVersions=[...new Set(s.map(x=>String(x.version||"").trim()).filter(Boolean))];

  $("buildMismatch").innerHTML=fingerprintMismatch?(
    `<div class="mismatch-panel"><div class="panel-title"><div><span class="section-kicker">BUILD MISMATCH</span><h3>Build information</h3></div><span class="count-badge danger">${format(builds.length)} builds</span></div><p>Reports with the same build fingerprint are grouped into one build entry.</p><div class="fingerprint-table">${builds.map((x,i)=>`<div class="fingerprint-row"><strong>Build ${String.fromCharCode(65+i)}</strong><span><b>Suite:</b> ${esc((x.suites||[]).join(", ")||"Not detected")}<br><b>Test Suite Version:</b> ${esc((s.filter(item=>(x.suites||[]).includes(item.name)&&item.fingerprint===x.fingerprint).map(item=>item.version).filter(Boolean).join(", "))||"Not detected")}<br><b>Fingerprint:</b> ${esc(x.fingerprint||"Not detected")}<br><b>Android:</b> ${esc(x.androidVersion||"Not detected")}<br><b>Security Patch:</b> ${esc(x.securityPatch||"Not detected")}<br><b>Build ID:</b> ${esc(x.buildId||"Not detected")}<br><b>SDK:</b> ${esc(x.sdk||"Not detected")}<br><b>Architecture:</b> ${esc(x.abis||"Not detected")}</span></div>`).join("")}</div></div>`
  ):"";

  $("buildInfoCard").innerHTML=fingerprintMismatch?"":`
    <section class="build-info-section">
      <div class="build-info-header">
        <div><span class="section-kicker">BUILD INFORMATION</span><h3>Device build details</h3></div>
        <span class="build-info-count">${format(builds.length)} build${builds.length===1?"":"s"}</span>
      </div>
      <div class="build-info-grid">
        <div class="build-info-item wide"><span>Build Fingerprint</span><strong>${esc(primaryBuild.fingerprint||d.buildFingerprint||"Not detected")}</strong></div>
        <div class="build-info-item"><span>Android Version</span><strong>${esc(primaryBuild.androidVersion||d.androidVersion||"Not detected")}</strong></div>
        <div class="build-info-item"><span>Security Patch</span><strong>${esc(primaryBuild.securityPatch||d.securityPatch||"Not detected")}</strong></div>
        <div class="build-info-item"><span>Build ID</span><strong>${esc(primaryBuild.buildId||"Not detected")}</strong></div>
        <div class="build-info-item"><span>SDK Version</span><strong>${esc(primaryBuild.sdk||"Not detected")}</strong></div>
        <div class="build-info-item"><span>Architecture</span><strong>${esc(primaryBuild.abis||"Not detected")}</strong></div>
        <div class="build-info-item"><span>Suites in This Build</span><strong>${esc((primaryBuild.suites||[]).join(", ")||"Not detected")}</strong></div>
      </div>
    </section>`;

  const ready=s.length&&Number(o.failed||0)===0&&inc.length===0&&!fingerprintMismatch;

  // A build mismatch is a hard stop. Show only build information; do not
  // present test-case/module counts from mixed builds.
  const statsEl=$("stats");
  const suiteEl=$("suiteGrid");
  const issuesEl=$("issuesGrid");
  if(fingerprintMismatch){
    statsEl.innerHTML="";
    suiteEl.innerHTML="";
    if(issuesEl) issuesEl.classList.add("hidden");
    $("publishBtn").disabled=false;
    $("viewBtn").disabled=false;
    return;
  }
  if(issuesEl) issuesEl.classList.remove("hidden");
  $("readiness").textContent=fingerprintMismatch?"BUILD MISMATCH":(ready?"READY FOR REVIEW":"ATTENTION REQUIRED");
  $("readiness").className="readiness-chip "+(ready?"ready":"attention");
  const rate=((Number(o.passed||0)/Math.max(1,Number(o.totalTests||0)))*100).toFixed(1);
  $("stats").innerHTML=[
    ["PASSED",format(o.passed),"Passed test cases","pass"],
    ["FAILED",format(o.failed),"Failed test cases","fail"],
    ["ASSUMPTION FAILURE",format(o.assumptionFailures),"Assumption failures","warn"],
    ["IGNORED",format(o.ignored),"Ignored test cases","warn"],
    ["WARNINGS",format(o.warnings),"Tradefed warnings","warn"],
    ["TOTAL TESTS",format(o.totalTests),rate+"% pass rate","total"]
  ].map(x=>`<div class="stat ${x[3]}"><span>${x[0]}</span><strong>${x[1]}</strong><small>${x[2]}</small></div>`).join("");

  $("suiteGrid").innerHTML=s.map(x=>{
    const p=x.modules?Math.round(x.completedModules/x.modules*100):0;
    return `<article class="suite"><div class="suite-top"><div class="suite-title"><h3>${esc(x.name)}</h3></div><span class="pill ${x.status==="COMPLETED"?"ok":"warn"}">${esc(x.status)}</span></div><div class="suite-number">${format(x.completedModules)} / ${format(x.modules)} modules</div><div class="progress"><i style="width:${p}%"></i></div><div class="suite-meta"><span>${p}% complete</span><span>${format(x.testCases)} total tests</span></div><div class="suite-version"><span>Test Suite Version</span><strong>${esc(x.version||"Not detected")}</strong></div><div class="suite-fails"><span class="good">${format(x.passed)} passed</span> · <span class="bad">${format(x.failed)} failed</span> · ${format(x.assumptionFailures)} assumption failure · ${format(x.ignored)} ignored · ${format(x.warnings)} warnings</div></article>`;
  }).join("");

  $("incompleteCount").textContent=inc.length;
  $("failureCount").textContent=fail.length;
  renderJiraStatus();
  $("incompleteList").innerHTML=inc.length?inc.map(x=>`<div class="issue-row"><strong>${esc(x.suite)} · ${esc(x.module)}</strong><small>${esc(x.reason||"Module incomplete")}</small>${jiraMatchesMarkup(x)}</div>`).join(""):"<div class='empty'>No incomplete modules.</div>";
  $("failureList").innerHTML=fail.length?fail.map(x=>`<div class="issue-row"><strong>${esc(x.suite)} · ${esc(x.module)} · ${esc(x.testCase)}</strong><small>${esc(x.details||"No failure details recorded.")}</small>${jiraMatchesMarkup(x)}</div>`).join(""):"<div class='empty'>No failures detected.</div>";
  $("publishBtn").disabled=false;$("viewBtn").disabled=false;
}
$("reportFiles").addEventListener("change",e=>{
  // Keep previously selected files when the user adds files in later selections.
  // De-duplicate by name, size and lastModified, since browsers expose a fresh
  // FileList for each selection and the input itself is not a persistent queue.
  const incoming=[...e.target.files];
  const key=f=>`${f.name}::${f.size}::${f.lastModified}`;
  const existing=new Set(state.files.map(key));
  for(const file of incoming){
    if(!existing.has(key(file))){
      state.files.push(file);
      existing.add(key(file));
    }
  }
  // Reset the native input so selecting the same file again still fires change.
  e.target.value="";
  renderFiles();
});
$("clearBtn").addEventListener("click",()=>{
  state.files=[];state.data=null;$("reportFiles").value="";renderFiles();
loadHistory();$("publishBtn").disabled=true;$("viewBtn").disabled=true;
  $("statusMessage").textContent="";$("stats").innerHTML="";$("suiteGrid").innerHTML="";
  $("incompleteList").innerHTML="";$("failureList").innerHTML="";
  $("incompleteCount").textContent="0";$("failureCount").textContent="0";
  $("buildMismatch").innerHTML="";
  $("buildInfoCard").innerHTML="";
  $("readiness").textContent="WAITING FOR REPORTS";$("readiness").className="readiness-chip";
  $("buildFingerprint").textContent="Not detected";
  $("androidVersion").textContent="Not detected";
  $("securityPatch").textContent="Not detected";
  const issuesEl=document.querySelector(".issues-grid");
  if(issuesEl) issuesEl.classList.add("hidden");
  $("readiness").textContent="WAITING FOR REPORTS";$("readiness").className="readiness-chip";
});
$("analyzeBtn").addEventListener("click",()=>{
  const b=$("analyzeBtn");b.disabled=true;$("clearBtn").disabled=true;b.textContent="Analyzing reports…";
  $("statusMessage").textContent="Starting upload…";setProgress(0,"Uploading reports…","Preparing ZIP files for the parser.");
  const fd=new FormData();state.files.forEach(f=>fd.append("files",f));const xhr=new XMLHttpRequest();xhr.open("POST","/api/analyze",true);
  xhr.upload.onprogress=e=>{if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);setProgress(pct,"Uploading reports…",`${formatBytes(e.loaded)} of ${formatBytes(e.total)} uploaded.`)}};
  xhr.upload.onload=()=>{setProgress(100,"Reports uploaded","Server is now scanning ZIP files and parsing Tradefed XML reports.",true);clearInterval(state.progressTimer);let phase=0;const phases=["Scanning ZIP files…","Reading Tradefed test_result.xml…","Merging suites and reruns…","Building certification dashboard…"];state.progressTimer=setInterval(()=>{phase=(phase+1)%phases.length;$("progressDetail").textContent=phases[phase]},900)};
  xhr.onerror=()=>finishAnalysis(new Error("Unable to connect to the analysis server."));xhr.ontimeout=()=>finishAnalysis(new Error("Analysis request timed out."));
  xhr.onload=()=>{try{const d=JSON.parse(xhr.responseText||"{}");if(xhr.status<200||xhr.status>=300)throw new Error(d.error||"Analysis failed");state.data=d;render();const diagnostics=d.reportDiagnostics||[],xmlCount=Number(d.xmlReportsFound||0),recognized=Number(d.recognizedReports||0),buildCount=(d.builds||[]).length,diagnosticErrors=diagnostics.flatMap(x=>(x.errors||[]).map(err=>`${x.file}: ${err}`));hideProgress();$("statusMessage").textContent=diagnosticErrors.length?`Analysis found ${xmlCount} XML report(s), recognized ${recognized}. ${diagnosticErrors.join(" | ")}`:`Analysis complete: ${xmlCount} XML report(s) • ${recognized} recognized • ${buildCount} build(s) • ${(d.suites||[]).length} suite(s).`}catch(e){finishAnalysis(e)}};
  xhr.send(fd);
  function finishAnalysis(error){hideProgress();$("statusMessage").textContent=error.message;$("readiness").textContent="ANALYSIS FAILED";$("readiness").className="readiness-chip attention";b.disabled=!state.files.length;$("clearBtn").disabled=!state.files.length;b.textContent="Analyze Reports →"}
  xhr.onloadend=()=>{if(xhr.status>=200&&xhr.status<300){b.disabled=!state.files.length;$("clearBtn").disabled=!state.files.length;b.textContent="Analyze Reports →"}};
});
async function getDashboardUrl(dashboard=state.data){
  if(!dashboard)throw new Error("Analyze reports first");
  const r=await fetch("/api/publish",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(dashboard)});
  if(!r.ok)throw new Error("Publish failed");
  return URL.createObjectURL(await r.blob());
}
$("viewBtn").addEventListener("click",async()=>{
  const b=$("viewBtn");b.disabled=true;b.textContent="Opening dashboard…";
  try{
    const url=await getDashboardUrl();
    const win=window.open(url,"_blank");
    if(!win)throw new Error("Popup blocked. Please allow popups for this site.");
    setTimeout(()=>URL.revokeObjectURL(url),60000);
  }catch(e){alert(e.message)}finally{b.disabled=false;b.textContent="View Dashboard ↗"}
});

async function loadHistory(){
  try{
    const r=await fetch("/api/history");
    if(!r.ok)throw new Error("Unable to load analysis history");
    const d=await r.json();
    const runs=d.runs||[],limit=Number(d.maxRuns||20);
    $("historyCount").textContent=`${runs.length} / ${limit}`;
    if(!runs.length){
      $("historyList").innerHTML="<div class='empty'>No successful analysis runs stored yet.</div>";
      return;
    }
    $("historyList").innerHTML=runs.map((run,index)=>{
      const date=run.analyzedAt?new Date(run.analyzedAt).toLocaleString("en-IN"):"Unknown";
      const statusClass=run.status==="READY FOR REVIEW"?"ready":(run.status==="BUILD MISMATCH"?"mismatch":"attention");
      return `<article class="history-row">
        <div class="history-run"><strong>#${runs.length-index}</strong><span>${esc(date)}</span></div>
        <div class="history-build"><span>BUILD</span><strong>${esc(run.buildFingerprint||"Not detected")}</strong></div>
        <div class="history-metrics"><span>${format(run.suiteCount)} suites</span><span>${format(run.totalTests)} tests</span><span>${format(run.failed)} failed</span></div>
        <span class="history-status ${statusClass}">${esc(run.status||"UNKNOWN")}</span>
        <div class="history-actions">
          <button class="secondary history-view" data-run-id="${esc(run.runId)}">View</button>
          <button class="primary history-download" data-run-id="${esc(run.runId)}">Download</button>
        </div>
      </article>`;
    }).join("");
    document.querySelectorAll(".history-view").forEach(btn=>btn.addEventListener("click",()=>openHistoryRun(btn.dataset.runId,false)));
    document.querySelectorAll(".history-download").forEach(btn=>btn.addEventListener("click",()=>openHistoryRun(btn.dataset.runId,true)));
  }catch(e){
    $("historyList").innerHTML=`<div class="empty">${esc(e.message)}</div>`;
  }
}
async function openHistoryRun(runId,download){
  let win=null;
  try{
    // Open the tab synchronously from the button click so browser popup
    // blockers do not reject the historical dashboard after the async fetch.
    if(!download){
      win=window.open("about:blank","_blank");
      if(!win)throw new Error("Popup blocked. Please allow popups for this site.");
      win.document.title="Preparing dashboard…";
      win.document.body.innerHTML="<p style='font-family:Arial;padding:24px'>Preparing historical dashboard…</p>";
    }

    const r=await fetch("/api/history/"+encodeURIComponent(runId));
    if(!r.ok)throw new Error("Historical run not found");
    const dashboard=await r.json();
    const url=await getDashboardUrl(dashboard);

    if(download){
      const a=document.createElement("a");
      a.href=url;
      a.download="gct-certification-dashboard-"+runId+".html";
      a.style.display="none";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    }else{
      win.location.href=url;
      setTimeout(()=>URL.revokeObjectURL(url),60000);
    }
  }catch(e){
    if(win && !win.closed) win.close();
    alert(e.message);
  }
}
$("publishBtn").addEventListener("click",async()=>{
  const b=$("publishBtn");b.disabled=true;b.textContent="Preparing dashboard…";
  try{
    const url=await getDashboardUrl(),a=document.createElement("a");
    a.href=url;a.download="gct-certification-dashboard.html";a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){alert(e.message)}finally{b.disabled=false;b.textContent="Download Dashboard HTML ↓"}
});
renderFiles();
loadHistory();
