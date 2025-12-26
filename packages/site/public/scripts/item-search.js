import Fuse from "./fuse.esm.js";

const dataNode = document.getElementById("items-data");
const grid = document.getElementById("items-grid");
const input = document.getElementById("item-search");
const count = document.getElementById("item-count");
const toggleGroupsButton = document.getElementById("toggle-groups");

let shouldExpandAll = false;
let isSearchActive = false;
let searchAutoExpanded = false;

const updateToggleButtonLabel = () => {
  if (!toggleGroupsButton) return;
  toggleGroupsButton.textContent = shouldExpandAll ? "Collapse all" : "Expand all";
};

const applyGroupExpansionState = () => {
  if (!grid) return;
  const details = grid.querySelectorAll("details[data-group]");
  details.forEach((node) => {
    node.open = shouldExpandAll;
  });
  updateToggleButtonLabel();
};

const updateSearchState = (query) => {
  const nextSearchActive = Boolean(query);

  if (nextSearchActive && !isSearchActive) {
    isSearchActive = true;
    if (!shouldExpandAll) {
      shouldExpandAll = true;
      searchAutoExpanded = true;
      updateToggleButtonLabel();
    }
  }

  if (!nextSearchActive && isSearchActive) {
    isSearchActive = false;
    if (searchAutoExpanded) {
      shouldExpandAll = false;
      searchAutoExpanded = false;
      updateToggleButtonLabel();
    }
  }
};

if (toggleGroupsButton) {
  updateToggleButtonLabel();
  toggleGroupsButton.addEventListener("click", () => {
    shouldExpandAll = !shouldExpandAll;
    searchAutoExpanded = false;
    applyGroupExpansionState();
  });
}

const formatGroupSegment = (segment) => {
  const withSpaces = segment
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/(\d)([a-zA-Z])/g, "$1 $2");

  return withSpaces
    .split(" ")
    .filter(Boolean)
    .map((word) => {
      if (/^\d+$/.test(word)) return word;
      if (word.length <= 1) return word.toUpperCase();
      return word[0].toUpperCase() + word.slice(1);
    })
    .join(" ");
};

const splitItemId = (id) => {
  const segments = String(id).split(".").filter(Boolean);
  if (segments[0] === "items") segments.shift();
  if (segments.length <= 1) return { groups: [], leaf: segments[0] ?? "" };
  return { groups: segments.slice(0, -1), leaf: segments.at(-1) ?? "" };
};

const toGroupDomId = (segments) =>
  ["group", ...segments]
    .join("-")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();

const buildGroupTree = (list) => {
  const root = {
    segment: "",
    label: "",
    path: [],
    children: new Map(),
    items: [],
  };

  list.forEach((item) => {
    const { groups } = splitItemId(item.id);
    let node = root;

    groups.forEach((segment) => {
      let next = node.children.get(segment);
      if (!next) {
        next = {
          segment,
          label: formatGroupSegment(segment),
          path: [...node.path, segment],
          children: new Map(),
          items: [],
        };
        node.children.set(segment, next);
      }
      node = next;
    });

    node.items.push(item);
  });

  return root;
};

const countGroupItems = (node) => {
  let total = node.items.length;
  node.children.forEach((child) => {
    total += countGroupItems(child);
  });
  return total;
};

const getSortedChildren = (node) =>
  [...node.children.values()].sort((a, b) => a.label.localeCompare(b.label));

const createItemCard = (item) => {
  const card = document.createElement("a");
  card.href = `/items/${encodeURIComponent(item.id)}`;
  card.className =
    "rounded-2xl border border-slate-800 bg-slate-900/60 p-5 transition hover:border-slate-600";

  const title = document.createElement("h3");
  title.className = "text-lg font-semibold text-white";
  title.textContent = item.name || item.id;

  const id = document.createElement("p");
  id.className = "mt-1 text-xs text-slate-400";
  id.textContent = item.id;

  const description = document.createElement("p");
  description.className = "mt-3 text-sm text-slate-300";
  description.textContent = item.description || "No description yet.";

  card.appendChild(title);
  card.appendChild(id);
  card.appendChild(description);

  return card;
};

const createGroupSummary = (level, id, label, totalCount) => {
  const labelClassName =
    level === 0
      ? "text-xl font-semibold text-white md:text-2xl"
      : level === 1
        ? "text-lg font-semibold text-white"
        : level === 2
          ? "text-base font-semibold text-white"
          : "text-sm font-semibold text-white";

  const summary = document.createElement("summary");
  summary.id = id;
  summary.className = "cursor-pointer select-none p-5 [&::-webkit-details-marker]:hidden";

  const row = document.createElement("div");
  row.className = "flex items-center justify-between gap-3";

  const labelNode = document.createElement("span");
  labelNode.className = labelClassName;
  labelNode.textContent = label;

  const countNode = document.createElement("span");
  countNode.className = "rounded-full bg-white/10 px-2 py-1 text-xs text-slate-200";
  countNode.textContent = String(totalCount);

  row.appendChild(labelNode);
  row.appendChild(countNode);

  summary.appendChild(row);
  return summary;
};

const renderGroupDetails = (node, level) => {
  const children = getSortedChildren(node);
  const items = [...node.items].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id));
  const totalCount = countGroupItems(node);
  const headingId = toGroupDomId(node.path);

  const details = document.createElement("details");
  details.className =
    "rounded-2xl border border-slate-800 bg-slate-900/60 transition hover:border-slate-600";
  details.setAttribute("data-group", "");
  details.setAttribute("aria-labelledby", headingId);

  details.appendChild(createGroupSummary(level, headingId, node.label, totalCount));

  const content = document.createElement("div");
  content.className = "px-5 pb-5 space-y-8";

  if (items.length) {
    const itemsGrid = document.createElement("div");
    itemsGrid.className = "grid gap-4 md:grid-cols-2";
    items.forEach((item) => itemsGrid.appendChild(createItemCard(item)));
    content.appendChild(itemsGrid);
  }

  if (children.length) {
    const childContainer = document.createElement("div");
    childContainer.className = "space-y-8 border-l border-slate-800 pl-5";
    children.forEach((child) => {
      childContainer.appendChild(renderGroupDetails(child, level + 1));
    });
    content.appendChild(childContainer);
  }

  if (content.childNodes.length) {
    details.appendChild(content);
  }

  return details;
};

const renderGrouped = (list) => {
  grid.textContent = "";

  const root = buildGroupTree(list);
  const fragment = document.createDocumentFragment();

  if (root.items.length) {
    const ungroupedNode = {
      label: "Ungrouped",
      path: ["ungrouped"],
      children: new Map(),
      items: root.items,
    };

    const details = document.createElement("details");
    details.className =
      "rounded-2xl border border-slate-800 bg-slate-900/60 transition hover:border-slate-600";
    details.setAttribute("data-group", "");
    details.setAttribute("aria-labelledby", "group-ungrouped");

    details.appendChild(createGroupSummary(0, "group-ungrouped", "Ungrouped", root.items.length));

    const content = document.createElement("div");
    content.className = "px-5 pb-5 space-y-8";

    const itemsGrid = document.createElement("div");
    itemsGrid.className = "grid gap-4 md:grid-cols-2";
    [...ungroupedNode.items]
      .sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id))
      .forEach((item) => itemsGrid.appendChild(createItemCard(item)));

    content.appendChild(itemsGrid);
    details.appendChild(content);

    fragment.appendChild(details);
  }

  getSortedChildren(root).forEach((child) => {
    fragment.appendChild(renderGroupDetails(child, 0));
  });

  grid.appendChild(fragment);
  count.textContent = String(list.length);

  applyGroupExpansionState();
};

if (!dataNode || !grid || !input || !count) {
  console.warn("Item search: missing elements", {
    dataNode,
    grid,
    input,
    count,
    toggleGroupsButton,
  });
} else {
  const rawJson = dataNode.textContent?.trim() ?? "";
  const data = rawJson ? JSON.parse(rawJson) : [];
  const fuse = new Fuse(data, {
    keys: ["name", "id", "description"],
    threshold: 0.3,
    ignoreLocation: true,
  });

  renderGrouped(data);

  input.addEventListener("input", (event) => {
    const query = event.target.value.trim();
    updateSearchState(query);

    if (!query) {
      renderGrouped(data);
      return;
    }

    const results = fuse.search(query).map((result) => result.item);
    renderGrouped(results);
  });
}
