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
    $("status").textContent = "Търсене в " + (category === "phone" ? "8" : "3") + " сайта едновременно…";

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

function normalizeToEuro(priceStr) {
    if (!priceStr || priceStr === "N/A") return "";

    let str = priceStr.trim().replace(/^Цена\s*:\s*/i, '');

    const masterClubEuroMatch = str.match(/^(\d{3,})\s*€/);
    if (masterClubEuroMatch && !str.includes('.')) {
        const rawCents = parseInt(masterClubEuroMatch[1], 10);
        return (rawCents / 100).toFixed(2) + " €";
    }

    const prefixEuroMatch = str.match(/€\s*(\d+[\.,]\d{1,2})/);
    if (prefixEuroMatch) {
        const val = parseFloat(prefixEuroMatch[1].replace(',', '.'));
        if (!isNaN(val)) return val.toFixed(2) + " €";
    }

    const suffixEuroMatch = str.match(/(\d+[\.,]\d{1,2})\s*€/);
    if (suffixEuroMatch) {
        const val = parseFloat(suffixEuroMatch[1].replace(',', '.'));
        if (!isNaN(val)) return val.toFixed(2) + " €";
    }

    const intEuroMatch = str.match(/(\d+)\s*€/);
    if (intEuroMatch) {
        const val = parseFloat(intEuroMatch[1]);
        if (!isNaN(val)) return val.toFixed(2) + " €";
    }

    const bgnMatch = str.match(/(\d+[\.,]?\d*)\s*лв/i);
    if (bgnMatch) {
        const val = parseFloat(bgnMatch[1].replace(',', '.'));
        if (!isNaN(val)) {
            return (val / 1.95583).toFixed(2) + " €";
        }
    }

    const numMatch = str.match(/\d+[\.,]?\d*/);
    if (numMatch) {
        const val = parseFloat(numMatch[0].replace(',', '.'));
        if (!isNaN(val)) {
            return (val / 1.95583).toFixed(2) + " €";
        }
    }

    return str;
}

function formatItemData(it) {
    let title = it.title || "";
    let price = (it.price && it.price !== "N/A") ? it.price : "";
    let url = it.url || "";

    if (url.includes('masterclub.info')) {
        const mcMatch = title.match(/(.*?)\s*[–\-]\s*(\d+)$/);
        if (mcMatch) {
            title = mcMatch[1].trim();
            if (!price) price = mcMatch[2];
        }
    }

    if (url.includes('cellphone-bg.com')) {
        title = title.replace(/Баркод/, ' Баркод').replace(/Наличен/i, ' Наличен');
    }

    if (url.includes('bazar.bg')) {
        const locMatch = title.match(/(гр\.|с\.)\s*[А-Яа-я]/i);
        if (locMatch) {
            const tail = title.substring(locMatch.index); 
            title = title.substring(0, locMatch.index).trim(); 

            if (!price) {
                const priceMatch = tail.match(/(\d[\d\s.,]*(?:€|лв).*)/i);
                if (priceMatch) {
                    price = priceMatch[1].split('-')[0].trim();
                }
            }
        }
    }

    if (url.includes('laptopremont.com')) {
        const lrMatch = title.match(/(.*?)\s*:\s*([\d.]+\s*€[\d.]+\s*лв\.)/i);
        if (lrMatch) {
            title = lrMatch[1].trim(); 
            if (!price) price = lrMatch[2].trim();
        } else {
            title = title.replace(/\s*:\s*Онлайн магазин Laptop Remont/i, '').trim();
        }
    }

    if (url.includes('siaifon.com')) {
        if (title.includes("— Цена:")) {
            const parts = title.split("— Цена:");
            title = parts[0].trim();
            if (!price) price = parts[1].trim();
        }
    }

    const dashIndex = title.lastIndexOf(' — ');
    if (dashIndex !== -1) {
        const afterDash = title.substring(dashIndex + 3);
        if (/[€лв]/i.test(afterDash)) {
            title = title.substring(0, dashIndex).trim();
            if (!price) price = afterDash.trim();
        }
    }

    const displayPrice = normalizeToEuro(price);

    return { displayTitle: title, displayPrice };
}

function render(data) {
    const total = data.results.reduce((n, s) => n + s.items.length, 0);
    $("status").innerHTML =
        `Готово: <b>${total}</b> резултата` +
        (data.cached ? " · от кеша (мигновено)" : ` · ${data.total_seconds}s`);

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

                const { displayTitle, displayPrice } = formatItemData(it);

                const priceBadge = displayPrice 
                    ? `<span class="price-badge">${esc(displayPrice)}</span>` 
                    : '';

                a.innerHTML = `
                    <div class="item-info">
                        <span class="item-title">${esc(displayTitle)}</span>
                        <span class="u">${esc(it.url)}</span>
                    </div>
                    ${priceBadge}
                `;

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
