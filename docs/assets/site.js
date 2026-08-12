(function () {
  document.querySelectorAll(".home-hero-image img, .issue-image img, .archive-image img").forEach((image) => {
    image.addEventListener("error", () => {
      const figure = image.closest(".home-hero-image, .issue-image, .archive-image");
      if (figure) figure.hidden = true;
    }, { once: true });
  });
  const input = document.querySelector("#search-input");
  if (!input) return;
  const typeFilter = document.querySelector("#type-filter");
  const topicFilter = document.querySelector("#topic-filter");
  const results = document.querySelector("#search-results");
  const count = document.querySelector("#result-count");
  let entries = [];

  const esc = (value) => String(value || "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
  const safeUrl = (value) => /^https?:\/\//i.test(value || "") ? value : "";
  const formatDate = (value) => {
    const parsed = new Date(`${value}T12:00:00Z`);
    return Number.isNaN(parsed.valueOf()) ? value : new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" }).format(parsed);
  };
  function syncUrl() {
    const params = new URLSearchParams();
    if (input.value.trim()) params.set("q", input.value.trim());
    if (typeFilter.value !== "All") params.set("type", typeFilter.value);
    if (topicFilter.value !== "All topics") params.set("topic", topicFilter.value);
    history.replaceState({}, "", `index.html${params.size ? `?${params}` : ""}`);
  }
  function render() {
    const needle = input.value.toLowerCase().trim();
    const filtered = entries.filter((item) => {
      const haystack = [item.title, item.source, item.text, ...(item.topics || [])].join(" ").toLowerCase();
      return (!needle || haystack.includes(needle)) && (typeFilter.value === "All" || item.type === typeFilter.value) && (topicFilter.value === "All topics" || (item.topics || []).includes(topicFilter.value));
    });
    count.textContent = `${filtered.length} result${filtered.length === 1 ? "" : "s"}`;
    if (!filtered.length) {
      results.innerHTML = '<div class="empty-state compact"><h2>No matching entries</h2><p>Try a broader phrase or clear one of the filters.</p></div>';
      return;
    }
    results.innerHTML = filtered.map((item) => {
      const tags = (item.topics || []).map((topic) => `<span>${esc(topic)}</span>`).join("");
      const source = [item.source, item.publishedDate].filter(Boolean).join(" · ");
      const original = safeUrl(item.url) ? `<a class="original-link" href="${esc(item.url)}" target="_blank" rel="noreferrer">Read the original ↗</a>` : "";
      return `<article class="result-card"><div><span class="format-label">${esc(item.type)}</span><span>${esc(formatDate(item.issueDate))}</span></div><h2>${esc(item.title)}</h2><p class="source-line">${esc(source || "Independent analysis")}</p><p>${esc(String(item.text || "").split("\n\n")[0])}</p>${tags ? `<div class="topic-row">${tags}</div>` : ""}<div class="result-links"><a href="../issues/${esc(item.issueDate)}/index.html">View in issue →</a>${original}</div></article>`;
    }).join("");
  }
  const params = new URLSearchParams(location.search);
  input.value = params.get("q") || "";
  if ([...typeFilter.options].some((option) => option.value === params.get("type"))) typeFilter.value = params.get("type");
  if ([...topicFilter.options].some((option) => option.value === params.get("topic"))) topicFilter.value = params.get("topic");
  [input, typeFilter, topicFilter].forEach((control) => control.addEventListener("input", () => { syncUrl(); render(); }));
  fetch("../search-index.json").then((response) => {
    if (!response.ok) throw new Error("Search index unavailable");
    return response.json();
  }).then((data) => { entries = Array.isArray(data) ? data : []; render(); }).catch(() => {
    results.innerHTML = '<div class="empty-state compact"><h2>Search is temporarily unavailable</h2><p>The published issues remain available in the archive.</p></div>';
  });
})();
