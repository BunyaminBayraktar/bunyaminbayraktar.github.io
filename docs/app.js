let DATA = null;
let currentView = "ps5";
let currentList = "transfers";
let toastTimer = null;
let TEAM_ROWS = new Map();

const STORAGE_KEY = "fc26-control-progress-v1";
const LIST_VIEWS = new Set(["transfers", "creates", "exists", "unresolved"]);
const VALID_VIEWS = new Set(["ps5", "pc", ...LIST_VIEWS]);
const initialParams = new URLSearchParams(window.location.search);
const initialState = {
  view: VALID_VIEWS.has(initialParams.get("view")) ? initialParams.get("view") : "ps5",
  team: initialParams.get("team") || "",
  query: initialParams.get("q") || "",
  status: initialParams.get("status") || ""
};

function loadProgress(){
  try{
    const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  }catch{
    return {};
  }
}

function saveProgress(progress){
  localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
}

function esc(value){
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function fmt(number){
  return Number(number || 0).toLocaleString("tr-TR");
}

function percent(done, total){
  return total ? Math.round((done / total) * 100) : 0;
}

function normalize(value){
  return String(value || "").toLocaleLowerCase("tr-TR");
}

function progressByStatus(status){
  const progress = loadProgress();
  return new Set(
    Object.entries(progress)
      .filter(([, value]) => value?.status === status)
      .map(([key]) => key)
  );
}

function progressDoneKeys(){
  return progressByStatus("done");
}

function transfersForTeam(team){
  return TEAM_ROWS.get(team) || [];
}

function teamStats(done = progressDoneKeys()){
  return [...TEAM_ROWS.entries()].map(([team, rows]) => {
    const completed = rows.filter(row => done.has(row.key)).length;
    return {
      team,
      rows,
      completed,
      pending: rows.length - completed,
      percent: percent(completed, rows.length)
    };
  }).sort((a, b) => {
    if((a.pending === 0) !== (b.pending === 0)) return a.pending === 0 ? 1 : -1;
    if(a.pending !== b.pending) return b.pending - a.pending;
    return a.team.localeCompare(b.team, "tr");
  });
}

function renderSidebar(){
  const done = progressDoneKeys();
  const completed = DATA.transfers.filter(row => done.has(row.key)).length;
  document.querySelector("#sidebarDone").textContent = fmt(completed);
  document.querySelector("#sidebarRemaining").textContent = fmt(DATA.transfers.length - completed);
}

function renderPC(){
  document.querySelector("#pcTransferCount").textContent = fmt(DATA.transfers.length);
  renderSidebar();
}

function renderTeamSelect(keepValue = true, done = progressDoneKeys()){
  const select = document.querySelector("#teamSelect");
  const oldValue = keepValue ? select.value : initialState.team;
  const stats = teamStats(done);

  select.innerHTML = stats.map(item => {
    const label = item.pending ? `${item.team} — ${item.pending} kaldı` : `✓ ${item.team} — tamamlandı`;
    return `<option value="${esc(item.team)}">${esc(label)}</option>`;
  }).join("");

  if(oldValue && TEAM_ROWS.has(oldValue)) select.value = oldValue;
}

function currentQueue(team){
  const progress = loadProgress();
  const normal = [];
  const skipped = [];

  for(const row of transfersForTeam(team)){
    const state = progress[row.key]?.status;
    if(state === "done") continue;
    if(state === "skipped") skipped.push(row);
    else normal.push(row);
  }
  return normal.concat(skipped);
}

function renderTeamProgressGrid(){
  const done = progressDoneKeys();
  const selectedTeam = document.querySelector("#teamSelect").value;
  const query = normalize(document.querySelector("#teamSearchInput").value.trim());
  const status = document.querySelector("#teamStatusFilter").value;
  const stats = teamStats(done);
  const completedTeams = stats.filter(item => item.pending === 0).length;

  document.querySelector("#teamSummary").textContent =
    `${completedTeams}/${stats.length} takım tamamlandı`;

  const filteredTeams = stats.filter(item => {
    const isComplete = item.pending === 0;
    return (!query || normalize(item.team).includes(query)) &&
      (status === "all" || (status === "complete" ? isComplete : !isComplete));
  });

  const grid = document.querySelector("#teamProgressGrid");
  if(!filteredTeams.length){
    grid.innerHTML = `<div class="empty-state"><strong>Eşleşen takım bulunamadı.</strong><span>Aramayı veya durum filtresini değiştir.</span></div>`;
    return;
  }

  grid.innerHTML = filteredTeams.map(item => {
    const complete = item.pending === 0;
    return `
      <button class="team-card ${complete ? "complete-team" : ""} ${item.team === selectedTeam ? "active" : ""}" data-team="${esc(item.team)}" type="button">
        <div class="team-card-top">
          <span class="team-card-name">${complete ? "✓ " : ""}${esc(item.team)}</span>
          <span class="team-card-count">${item.completed}/${item.rows.length}</span>
        </div>
        <div class="team-mini-track"><div class="team-mini-bar" style="width:${item.percent}%"></div></div>
        <div class="team-card-bottom"><span>${complete ? "Tamamlandı" : `${item.pending} transfer kaldı`}</span><strong>%${item.percent}</strong></div>
      </button>`;
  }).join("");

  grid.querySelectorAll(".team-card").forEach(card => {
    card.addEventListener("click", () => {
      document.querySelector("#teamSelect").value = card.dataset.team;
      renderPS5();
      syncUrl();
      document.querySelector(".toolbar").scrollIntoView({behavior:"smooth", block:"start"});
    });
  });
}

function renderPS5(){
  const done = progressDoneKeys();
  const completed = DATA.transfers.filter(row => done.has(row.key)).length;
  const total = DATA.transfers.length;

  document.querySelector("#totalTransfers").textContent = fmt(total);
  document.querySelector("#doneTransfers").textContent = fmt(completed);
  document.querySelector("#remainingTransfers").textContent = fmt(total - completed);
  document.querySelector("#donePercent").textContent = `%${percent(completed, total)} tamamlandı`;

  renderSidebar();
  renderTeamSelect(true, done);

  const team = document.querySelector("#teamSelect").value;
  if(!team){
    document.querySelector("#currentCard").innerHTML = `<div class="complete"><div><strong>Transfer bulunamadı</strong><small>Yüklü veride hedef takım bulunmuyor.</small></div></div>`;
    renderTeamProgressGrid();
    return;
  }

  const teamRows = transfersForTeam(team);
  const teamDone = teamRows.filter(row => done.has(row.key)).length;
  const teamPending = teamRows.length - teamDone;
  const teamPercent = percent(teamDone, teamRows.length);

  document.querySelector("#teamProgressText").textContent = `${team}: ${teamDone}/${teamRows.length} tamamlandı`;
  document.querySelector("#teamProgressPercent").textContent = `%${teamPercent}`;
  const progressTrack = document.querySelector(".progress-track");
  progressTrack.setAttribute("aria-valuenow", String(teamPercent));
  document.querySelector("#teamProgressBar").style.width = `${teamPercent}%`;

  const queue = currentQueue(team);
  const current = queue[0];

  if(!current){
    document.querySelector("#currentCard").innerHTML = `
      <div class="complete"><div>
        <span class="complete-icon">✓</span>
        <strong>${esc(team)} tamamlandı</strong>
        <small>Bu takıma ait ${teamRows.length} transferin tamamı işlendi.</small>
      </div></div>`;
    document.querySelector("#doneBtn").disabled = true;
    document.querySelector("#skipBtn").disabled = true;
    document.querySelector("#nextPlayers").innerHTML = "";
    renderTeamProgressGrid();
    return;
  }

  document.querySelector("#doneBtn").disabled = false;
  document.querySelector("#skipBtn").disabled = false;

  const progress = loadProgress();
  const revisit = progress[current.key]?.status === "skipped";
  document.querySelector("#currentCard").innerHTML = `
    <div class="kicker">${revisit ? "DAHA ÖNCE ATLANDI" : "SIRADAKİ TRANSFER"}</div>
    <div class="player">${esc(current.player)}</div>
    <div class="route">
      <span class="route-team">${esc(current.source)}</span>
      <span class="arrow">→</span>
      <span class="route-team target">${esc(current.target)}</span>
    </div>
    <div class="meta">
      <div class="meta-item"><div class="meta-label">FC PLAYER ID</div><div class="meta-value">${esc(current.fc_id)}</div></div>
      <div class="meta-item"><div class="meta-label">TRANSFERMARKT ID</div><div class="meta-value">${esc(current.tm_id)}</div></div>
      <div class="meta-item"><div class="meta-label">TAKIMDA KALAN</div><div class="meta-value">${teamPending}</div></div>
    </div>`;

  document.querySelector("#nextPlayers").innerHTML = queue.slice(1, 6).map((row, index) => {
    const skipped = progress[row.key]?.status === "skipped";
    return `
      <div class="next-card">
        <div><span class="next-index">${index + 2}</span><span class="next-name">${esc(row.player)}</span></div>
        <div class="next-route">${esc(row.source)} → ${esc(row.target)}${skipped ? ` <span class="skipped-note">• daha önce atlandı</span>` : ""}</div>
      </div>`;
  }).join("") || `<p class="next-route">Bu takımdaki son oyuncudasın.</p>`;

  renderTeamProgressGrid();
}

function markCurrent(status){
  const team = document.querySelector("#teamSelect").value;
  const row = currentQueue(team)[0];
  if(!row) return;

  const progress = loadProgress();
  progress[row.key] = {
    status,
    player: row.player,
    source: row.source,
    target: row.target,
    at: new Date().toISOString()
  };
  saveProgress(progress);
  renderPS5();
}

function undoLast(){
  const progress = loadProgress();
  const actions = Object.entries(progress)
    .filter(([, value]) => value?.status === "done" || value?.status === "skipped")
    .sort((a, b) => String(b[1].at || "").localeCompare(String(a[1].at || "")));

  if(!actions.length){
    showToast("Geri alınacak işlem bulunmuyor.");
    return;
  }
  delete progress[actions[0][0]];
  saveProgress(progress);
  renderPS5();
  showToast("Son işlem geri alındı.");
}

function resetAll(){
  if(confirm("Bu tarayıcıdaki tüm YAPILDI / ATLA ilerlemesi silinsin mi?")){
    localStorage.removeItem(STORAGE_KEY);
    renderPS5();
    showToast("İlerleme sıfırlandı.");
  }
}

function rowStatus(row, progress = loadProgress()){
  if(currentList !== "transfers") return "neutral";
  return progress[row.key]?.status || "pending";
}

function statusLabel(status){
  return {done:"Yapıldı", skipped:"Atlandı", pending:"Yapılmadı", neutral:"—"}[status] || "—";
}

function renderList(){
  const source = DATA[currentList] || [];
  const query = normalize(document.querySelector("#searchInput").value.trim());
  const team = document.querySelector("#filterTeam").value;
  const status = document.querySelector("#filterStatus").value;
  const progress = loadProgress();

  const filtered = source.filter(row => {
    const haystack = normalize(`${row.player} ${row.source} ${row.target} ${row.fc_id} ${row.tm_id}`);
    const matchesStatus = currentList !== "transfers" || !status || rowStatus(row, progress) === status;
    return (!query || haystack.includes(query)) &&
      (!team || row.source === team || row.target === team) && matchesStatus;
  });

  const titles = {
    transfers:"Transferler",
    creates:"Create Oyuncular",
    exists:"Mevcut Oyuncular",
    unresolved:"İnceleme"
  };
  const shown = Math.min(filtered.length, 1000);
  document.querySelector("#listTitle").textContent = titles[currentList];
  document.querySelector("#listCount").textContent = filtered.length > 1000
    ? `${fmt(filtered.length)} kayıt • ilk ${fmt(shown)} gösteriliyor`
    : `${fmt(filtered.length)} kayıt`;

  document.querySelector("#tableBody").innerHTML = filtered.slice(0, 1000).map(row => {
    const statusValue = rowStatus(row, progress);
    return `
      <tr>
        <td><span class="status-pill ${statusValue}">${statusLabel(statusValue)}</span></td>
        <td class="player-cell"><strong>${esc(row.player)}</strong></td>
        <td>${esc(row.source)}</td>
        <td>${esc(row.target)}</td>
        <td>${esc(row.fc_id)}</td>
        <td>${esc(row.tm_id)}</td>
      </tr>`;
  }).join("");

  document.querySelector("#tableEmpty").hidden = filtered.length !== 0;
  document.querySelector("table").hidden = filtered.length === 0;
}

function rebuildListTeams(preferredValue = ""){
  const rows = DATA[currentList] || [];
  const teams = [...new Set(rows.flatMap(row => [row.source, row.target]).filter(team => team && team !== "-"))]
    .sort((a, b) => a.localeCompare(b, "tr"));
  const select = document.querySelector("#filterTeam");
  const oldValue = preferredValue || select.value;

  select.innerHTML = `<option value="">Tüm takımlar</option>` +
    teams.map(team => `<option value="${esc(team)}">${esc(team)}</option>`).join("");
  if(oldValue && teams.includes(oldValue)) select.value = oldValue;
}

function setView(view, updateUrl = true){
  currentView = VALID_VIEWS.has(view) ? view : "ps5";
  document.querySelectorAll(".nav-btn").forEach(button => {
    button.classList.toggle("active", button.dataset.view === currentView);
  });
  document.querySelector("#ps5View").classList.toggle("active", currentView === "ps5");
  document.querySelector("#pcView").classList.toggle("active", currentView === "pc");
  document.querySelector("#listView").classList.toggle("active", LIST_VIEWS.has(currentView));

  if(currentView === "ps5"){
    renderPS5();
  }else if(currentView === "pc"){
    renderPC();
  }else{
    currentList = currentView;
    rebuildListTeams();
    const statusFilter = document.querySelector("#filterStatus");
    statusFilter.hidden = currentList !== "transfers";
    if(currentList !== "transfers") statusFilter.value = "";
    renderList();
  }
  if(updateUrl) syncUrl();
}

function currentUrl(){
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("view", currentView);

  if(currentView === "ps5"){
    const team = document.querySelector("#teamSelect").value;
    if(team) url.searchParams.set("team", team);
  }else if(LIST_VIEWS.has(currentView)){
    const query = document.querySelector("#searchInput").value.trim();
    const team = document.querySelector("#filterTeam").value;
    const status = document.querySelector("#filterStatus").value;
    if(query) url.searchParams.set("q", query);
    if(team) url.searchParams.set("team", team);
    if(currentList === "transfers" && status) url.searchParams.set("status", status);
  }
  return url;
}

function syncUrl(){
  window.history.replaceState({}, "", currentUrl());
}

async function shareCurrent(){
  syncUrl();
  const url = window.location.href;
  try{
    if(navigator.share){
      await navigator.share({title:"FC26 Squad Sync", text:"FC26 kadro güncelleme görünümü", url});
      return;
    }
    await navigator.clipboard.writeText(url);
    showToast("Bağlantı panoya kopyalandı.");
  }catch(error){
    if(error?.name === "AbortError") return;
    const area = document.createElement("textarea");
    area.value = url;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    area.remove();
    showToast(copied ? "Bağlantı panoya kopyalandı." : "Bağlantı adres çubuğunda hazır.");
  }
}

function showToast(message){
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2600);
}

async function init(){
  try{
    const response = await fetch("./data.json", {cache:"no-store"});
    if(!response.ok) throw new Error("data.json bulunamadı");
    DATA = await response.json();
    TEAM_ROWS = DATA.transfers.reduce((map, row) => {
      if(row.target && row.target !== "-"){
        if(!map.has(row.target)) map.set(row.target, []);
        map.get(row.target).push(row);
      }
      return map;
    }, new Map());
  }catch{
    document.body.innerHTML = `
      <main class="main" style="margin:0;max-width:720px">
        <section class="complete" style="background:#fff;color:#526479">
          <div><strong style="color:#102033">Veri yüklenemedi</strong><small>Sayfayı yenilemeyi dene.</small></div>
        </section>
      </main>`;
    return;
  }

  document.querySelectorAll(".nav-btn").forEach(button => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  document.querySelector("#teamSelect").addEventListener("change", () => {renderPS5(); syncUrl();});
  document.querySelector("#doneBtn").addEventListener("click", () => markCurrent("done"));
  document.querySelector("#skipBtn").addEventListener("click", () => markCurrent("skipped"));
  document.querySelector("#undoBtn").addEventListener("click", undoLast);
  document.querySelector("#resetAllBtn").addEventListener("click", resetAll);
  document.querySelector("#shareTeamBtn").addEventListener("click", shareCurrent);
  document.querySelector("#shareListBtn").addEventListener("click", shareCurrent);
  document.querySelector("#teamSearchInput").addEventListener("input", renderTeamProgressGrid);
  document.querySelector("#teamStatusFilter").addEventListener("change", renderTeamProgressGrid);
  document.querySelector("#searchInput").addEventListener("input", () => {renderList(); syncUrl();});
  document.querySelector("#filterTeam").addEventListener("change", () => {renderList(); syncUrl();});
  document.querySelector("#filterStatus").addEventListener("change", () => {renderList(); syncUrl();});

  renderTeamSelect(false);
  document.querySelector("#searchInput").value = initialState.query;
  document.querySelector("#filterStatus").value = ["pending", "done", "skipped"].includes(initialState.status) ? initialState.status : "";
  if(LIST_VIEWS.has(initialState.view)){
    currentList = initialState.view;
    rebuildListTeams(initialState.team);
  }
  setView(initialState.view, false);
  if(LIST_VIEWS.has(initialState.view)){
    rebuildListTeams(initialState.team);
    renderList();
  }
  syncUrl();
}

init();
