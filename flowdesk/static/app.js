"use strict";
const el = id => document.getElementById(id);
const node = (tag, text) => Object.assign(document.createElement(tag), {textContent: text});
const titles = {filter: "Filter event", set: "Set field", record: "Save record", deliver: "Send webhook"};
const defaults = {
  filter: {kind: "filter", field: "service", equals: "website"},
  set: {kind: "set", field: "subject", template: "Quote request from {{name}}"},
  record: {kind: "record"}, deliver: {kind: "deliver", destination: "crm"}
};
const sample = () => ({name: "Lead intake", steps: ["filter","set","record"].map(k => ({...defaults[k]}))});
let flow = sample(), selected = 0, saved = [], dirty = false, tab = "editor";
function message(text, error = false) {
  el("status").textContent = text;
  el("status").classList.toggle("error", error);
}
async function request(path, data) {
  const options = data === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)};
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "Request failed");
  return result;
}
const endpoint = action => "/api/workflows/" + flow.id + "/" + action;
function action(id, fn) {
  el(id).onclick = async () => {
    const button = el(id);
    button.disabled = true;
    try { await fn(); } catch (err) { message(err.message, true); }
    finally { button.disabled = false; }
  };
}
function changed() {
  dirty = true;
  el("title").textContent = flow.name || "Untitled workflow";
  el("result").hidden = true;
  message("Unsaved changes");
}
function library() {
  el("library").replaceChildren(...saved.map(item => {
    const b = node("button", item.name);
    b.setAttribute("aria-current", String(item.id === flow.id));
    b.onclick = () => { if (canLeave()) openFlow(item); };
    return b;
  }));
}
function canLeave() { return !dirty || confirm("Discard your unsaved changes?"); }
function openFlow(item) {
  flow = structuredClone(item); selected = 0; dirty = false;
  el("name").value = flow.name; el("title").textContent = flow.name;
  el("result").hidden = el("connection").hidden = true;
  message(flow.id ? "Saved · Revision " + flow.revision : "Draft · Save to enable testing and webhooks");
  library(); steps(); fields(); showTab("editor");
}
function steps() {
  el("count").textContent = flow.steps.length + (flow.steps.length === 1 ? " step" : " steps");
  el("steps").replaceChildren(...flow.steps.map((s, i) => {
    const b = node("button",""); b.className = "step";
    b.setAttribute("aria-pressed", String(i === selected));
    const icon = node("span", {filter:"≋",set:"ƒ",record:"▤",deliver:"↗"}[s.kind]);
    icon.className = "tile"; icon.setAttribute("aria-hidden","true");
    const label = node("span","");
    label.append(node("small","STEP " + String(i+1).padStart(2,"0")),node("strong",titles[s.kind]));
    b.append(icon,label); b.onclick = () => { selected = i; steps(); fields(); };
    return b;
  }));
}
function fields() {
  const s = flow.steps[selected], box = el("fields");
  box.replaceChildren();
  const label = node("label","Step type"), select = node("select","");
  for (const [kind, title] of Object.entries(titles)) {
    const o = node("option",title); o.value = kind; select.append(o);
  }
  select.value = s.kind; label.append(select); box.append(label);
  select.onchange = () => { flow.steps[selected] = {...defaults[select.value]}; changed(); steps(); fields(); };
  const labels = {field:"Field name",equals:"Equals (text)",template:"Text template",destination:"Destination alias"};
  for (const key of Object.keys(s).filter(k => k !== "kind")) {
    const l = node("label", labels[key]), input = node("input","");
    input.value = s[key]; input.oninput = () => { s[key] = input.value; changed(); };
    l.append(input); box.append(l);
  }
  const guidance = {filter:"Continue when the input field matches the text exactly.",set:"Insert payload fields with {{name}}.",record:"Store the current payload in this workflow’s records.",deliver:"Queue the payload for a named HTTPS destination configured on your worker."};
  const p = node("p",guidance[s.kind]); p.className="help"; box.append(p);
  const controls = node("div",""); controls.className = "buttons";
  for (const [text, offset] of [["Move up",-1],["Move down",1],["Remove",0]]) {
    const b = node("button",text), next = selected + offset;
    b.disabled = offset ? next < 0 || next >= flow.steps.length : flow.steps.length === 1;
    b.onclick = () => {
      flow.steps.splice(selected,1);
      if (offset) flow.steps.splice(next,0,s);
      selected = Math.min(next,flow.steps.length-1); changed(); steps(); fields();
    };
    controls.append(b);
  }
  box.append(controls);
}
function requireSaved() {
  if (!flow.id || dirty) throw new Error("Save your workflow before continuing.");
}
async function showTab(t) {
  tab = t;
  document.querySelectorAll("[data-tab]").forEach(b => b.setAttribute("aria-pressed",String(b.dataset.tab === t)));
  el("editor").hidden = t !== "editor"; el("activity").hidden = t === "editor";
  if (t === "editor") return;
  const names = {runs:"Run history",records:"Records",deliveries:"Deliveries"};
  el("activityTitle").textContent = names[t];
  el("items").replaceChildren();
  if (!flow.id) { el("items").append(node("p","Save and run a workflow to see activity here.")); return; }
  const id = flow.id, rows = await request(endpoint(t));
  if (flow.id !== id || t !== tab) return;
  if (!rows.length) el("items").append(node("p","No " + (t === "runs" ? "runs" : t) + " yet."));
  for (const row of rows) {
    const article = node("article",""), details = node("details","");
    const title = t === "runs" ? row.status + " · " + new Date(row.at).toLocaleString() :
      t === "deliveries" ? row.destination + " · " + row.status : "Record " + row.id;
    details.append(node("summary",title),node("pre",JSON.stringify(row,null,2)));
    article.append(details); el("items").append(article);
  }
}
el("name").oninput = e => { flow.name = e.target.value; changed(); };
action("add", () => {
  if (flow.steps.length >= 24) throw new Error("A workflow supports up to 24 steps.");
  flow.steps.push({...defaults.record}); selected = flow.steps.length-1; changed(); steps(); fields();
});
action("new", () => { if (canLeave()) openFlow({name:"Untitled workflow",steps:[{...defaults.record}]}); });
action("save", async () => {
  const definition = {name:flow.name,steps:flow.steps};
  const item = await (flow.id ? request(endpoint("save"),{definition,revision:flow.revision}) : request("/api/workflows",definition));
  saved = await request("/api/workflows"); openFlow(item);
});
for (const id of ["preview","run"]) action(id,async () => {
  requireSaved(); const result = await request(endpoint(id),{payload:JSON.parse(el("payload").value)});
  el("result").textContent = JSON.stringify(result,null,2); el("result").hidden = false;
  message((id === "preview" ? "Preview" : "Run") + " · " + result.status, result.status === "failed");
});
action("hook",async () => {
  requireSaved(); const {key} = await request(endpoint("key"));
  el("connection").textContent = "POST " + location.origin + "/hooks/" + flow.id + "\nContent-Type: application/json\nX-Flowdesk-Key: " + key;
  el("connection").hidden = false;
});
action("refresh",() => showTab(tab));
document.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => showTab(b.dataset.tab).catch(e => message(e.message,true)));
window.addEventListener("beforeunload",e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
request("/api/workflows").then(list => { saved = list; openFlow(list[0] || sample()); }).catch(e => message(e.message,true));
