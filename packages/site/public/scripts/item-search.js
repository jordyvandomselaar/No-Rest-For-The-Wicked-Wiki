import Fuse from "./fuse.esm.js";

const dataNode = document.getElementById("items-data");
const grid = document.getElementById("items-grid");
const input = document.getElementById("item-search");
const count = document.getElementById("item-count");

if (!dataNode || !grid || !input || !count) {
  console.warn("Item search: missing elements", { dataNode, grid, input, count });
} else {
  const rawJson = dataNode.textContent?.trim() ?? "";
  const data = rawJson ? JSON.parse(rawJson) : [];
  const fuse = new Fuse(data, {
    keys: ["name", "id", "description"],
    threshold: 0.3,
    ignoreLocation: true,
  });

  const render = (list) => {
    grid.innerHTML = "";
    const fragment = document.createDocumentFragment();
    list.forEach((item) => {
      const card = document.createElement("a");
      card.href = `/items/${encodeURIComponent(item.id)}`;
      card.className =
        "rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-slate-600";
      card.innerHTML = `
        <h3 class=\"text-lg font-semibold text-white\">${item.name}</h3>
        <p class=\"mt-1 text-xs text-slate-400\">${item.id}</p>
        <p class=\"mt-3 text-sm text-slate-300\">${item.description || "No description yet."}</p>
      `;
      fragment.appendChild(card);
    });
    grid.appendChild(fragment);
    count.textContent = String(list.length);
  };

  render(data);

  input.addEventListener("input", (event) => {
    const query = event.target.value.trim();
    if (!query) {
      render(data);
      return;
    }
    const results = fuse.search(query).map((result) => result.item);
    render(results);
  });
}
