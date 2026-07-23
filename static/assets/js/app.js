let category = "phone";
const $ = id => document.getElementById(id);

$("btnPhone").onclick = () => setCat("phone");
$("btnPc").onclick    = () => setCat("pc");
function setCat(c) {
    category = c;
    $("btnPhone").classList.toggle("active", c === "phone");
    $("btnPc").classList.toggle("active", c === "pc");
}

$("go").onclick = run;
$("q").addEventListener("keydown", e => { if (e.key === "Enter") run(); });

async function run() {
    const q = $("q").value.trim();
    if (q.length < 2) { $("status").textContent = "Въведи поне 2 символа."; return; }

    $("go").disabled = true;
    $("hint").style.display = "none";
    $("results").innerHTML = "";
    $("status").textContent = "Търсене в " + (category === "phone" ? "7" : "3") + " сайта едновременно…";

    try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&category=${category}`);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const data = await r.json();
        render(data);
    } catch (e) {
        $("status").textContent = "Грешка при заявката: " + e.message;
    } finally {
        $("go").disabled = false;
    }
}

function render(data) {
    const total = data.results.reduce((n, s) => n + s.items.length, 0);
    $("status").innerHTML =
        `Готово: <b>${total}</b> резултата` +
        (data.cached ? " · от кеша (мигновено)" : ` · ${data.total_seconds}s`);

    // сайтовете с най-много резултати — най-отгоре
    const sorted = [...data.results].sort((a, b) => b.items.length - a.items.length);
    const frag = document.createDocumentFragment();

    for (const s of sorted) {
        const card = document.createElement("div");
        card.className = "site-card";

        const head = document.createElement("div");
        head.className = "site-head";
        head.innerHTML =
            `<span class="dot ${s.ok ? "ok" : "err"}"></span>` +
            `<h2>${esc(s.site)}</h2>` +
            `<span class="count">${s.items.length}</span>` +
            `<span class="meta">${s.seconds ?? "–"}s</span>`;
        card.appendChild(head);

        const body = document.createElement("div");
        body.className = "site-body";

        if (!s.ok) {
            body.innerHTML = `<div class="error">${esc(s.error || "Грешка")}</div>`;
        } else if (s.items.length === 0) {
            body.innerHTML = `<div class="empty">Няма намерени резултати</div>`;
        } else {
            for (const it of s.items) {
                const a = document.createElement("a");
                a.className = "item";
                a.href = it.url;
                a.target = "_blank";
                a.rel = "noopener";
                
                // --- ADDED: Extract and format the scraped price ---
                const priceHtml = it.price && it.price !== "N/A" 
                    ? `<span class="price">${esc(it.price)}</span>` 
                    : '';
                
                // --- UPDATED: Insert price right after the title ---
                a.innerHTML = `${esc(it.title)} ${priceHtml}<span class="u">${esc(it.url)}</span>`;
                body.appendChild(a);
            }
        }
        card.appendChild(body);
        frag.appendChild(card);
    }
    $("results").appendChild(frag);
}

const esc = s => String(s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
