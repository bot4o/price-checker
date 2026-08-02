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

function formatItemData(it) {
    let title = it.title || "";
    let price = (it.price && it.price !== "N/A") ? it.price : "";
    let url = it.url || "";

    if (url.includes('masterclub.info')) {
        const mcMatch = title.match(/(.*?)\s*[–\-]\s*(\d+)$/);
        if (mcMatch) {
            title = mcMatch[1].trim();
            let p = mcMatch[2];
            price = p.length > 2 ? p.slice(0, -2) + "." + p.slice(-2) + " лв." : p + " лв.";
        } else if (/^\d+$/.test(price) && price.length > 2) {
            price = price.slice(0, -2) + "." + price.slice(-2) + " лв.";
        }
    }

    if (url.includes('cellphone-bg.com')) {
        title = title.replace(/Баркод/, ' Баркод').replace(/Наличен/i, ' Наличен');
    }

    // 3. Bazar.bg - Почистване на локация и интелигентно извличане на цена
    if (url.includes('bazar.bg')) {
        // Търсим къде започва локацията (обикновено с "гр." или "с.")
        const locMatch = title.match(/(гр\.|с\.)\s*[А-Яа-я]/i);
        
        if (locMatch) {
            // Взимаме всичко от града до края (напр. "гр. Варна, Гранд Мол28 юли260€508,52лв")
            const tail = title.substring(locMatch.index); 
            // Оставяме само чистото заглавие на продукта
            title = title.substring(0, locMatch.index).trim(); 

            // Ако бекендът не е подал цена, я "спасяваме" от опашката
            if (!price) {
                // Търсим първото число, което е последвано от валута (игнорира дати и квартали)
                const priceMatch = tail.match(/(\d[\d\s.,]*(?:€|лв).*)/i);
                if (priceMatch) {
                    let extractedPrice = priceMatch[1].trim();
                    
                    // Разделяме, ако са залепени евро и левове (напр. "260€508,52лв" -> "260€ / 508,52лв")
                    extractedPrice = extractedPrice.replace(/(\d[\d.,]*\s*€)\s*(\d[\d.,]*\s*лв\.?)/i, '$1 / $2');
                    
                    // Взимаме само първата част, ако има тире накрая (напр. "... - 470€")
                    price = extractedPrice.split('-')[0].trim();
                }
            }
        }
    }
    // 4. Laptopremont.com - Извличане на цена от заглавието
    if (url.includes('laptopremont.com')) {
        // Заглавието идва във формат: "Име на продукт : 2.60 €5.09 лв. : Онлайн магазин Laptop Remont"
        const lrMatch = title.match(/(.*?)\s*:\s*([\d.]+\s*€[\d.]+\s*лв\.)/i);

        if (lrMatch) {
            // Отрязваме заглавието само до името на продукта
            title = lrMatch[1].trim(); 

            // Спасяваме цената, ако скрейпърът не я е намерил
            if (!price) {
                let extractedPrice = lrMatch[2].trim();
                // Слагаме интервал и наклонена черта между еврото и левовете, за да е четимо (напр. "2.60 € / 5.09 лв.")
                price = extractedPrice.replace(/(€)([\d.]+)/, '$1 / $2');
            }
        } else {
            // Като резервен вариант, просто трием суфикса на магазина, ако случайно няма цена
            title = title.replace(/\s*:\s*Онлайн магазин Laptop Remont/i, '').trim();
        }
    }

    if (url.includes('siaifon.com')) {
        if (title.includes("— Цена:")) {
            const parts = title.split("— Цена:");
            title = parts[0].trim();
            price = parts[1].trim().replace(/(€[0-9.]+)([0-9.]+лв\.)/, '$1 / $2');
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

    // Връщаме изчистените данни
    return { displayTitle: title, displayPrice: price };
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

                // ИЗВИКВАМЕ функцията тук за всеки отделен продукт (it)
                const { displayTitle, displayPrice } = formatItemData(it);

                // Използваме вече ИЗЧИСТЕНИТЕ променливи displayPrice и displayTitle
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
