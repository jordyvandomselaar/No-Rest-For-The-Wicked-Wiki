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

const pluralize = (count, singular, plural = `${singular}s`) =>
  count === 1 ? singular : plural;

const createOutlineSvg = (className, pathD) => {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");

  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("d", pathD);

  svg.appendChild(path);
  return svg;
};

const getCountLabel = (node) => {
  const childCount = node.children.size;
  const totalItems = countGroupItems(node);

  if (childCount > 0) {
    return `${childCount} ${pluralize(childCount, "group")} · ${totalItems} ${pluralize(totalItems, "item")}`;
  }

  return `${node.items.length} ${pluralize(node.items.length, "item")}`;
};

const appendFormattedDescription = (element, value) => {
  element.textContent = "";
  const text = value || "No description yet.";
  const colorRegex = /<color=#[0-9a-fA-F]{6}>(.*?)<\/color>/g;
  let lastIndex = 0;
  let match;

  while ((match = colorRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      const segment = text.slice(lastIndex, match.index).replace(/<\/?color[^>]*>/gi, "");
      element.appendChild(document.createTextNode(segment));
    }
    const strong = document.createElement("strong");
    strong.textContent = match[1];
    element.appendChild(strong);
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    const segment = text.slice(lastIndex).replace(/<\/?color[^>]*>/gi, "");
    element.appendChild(document.createTextNode(segment));
  }
};

const createItemCard = (item) => {
  const card = document.createElement("a");
  card.href = `/items/${encodeURIComponent(item.id)}`;
  card.className =
    "block rounded-xl border border-slate-800 bg-gradient-to-r from-slate-950/40 to-slate-900/40 p-4 transition hover:border-slate-600";

  const header = document.createElement("div");
  header.className = "flex items-start justify-between gap-3";

  const title = document.createElement("h3");
  title.className = "font-semibold text-white";
  title.textContent = item.name || item.id;

  header.appendChild(title);

  if (item.assetGuid) {
    const pill = document.createElement("span");
    pill.className = "shrink-0 rounded bg-white/5 px-2 py-1 text-xs text-slate-300";
    pill.textContent = `ID: ${item.assetGuid}`;
    header.appendChild(pill);
  }

  const description = document.createElement("p");
  description.className = "mt-2 text-sm leading-relaxed text-slate-300";
  appendFormattedDescription(description, item.description);

  const codeRow = document.createElement("div");
  codeRow.className = "mt-3 text-xs text-slate-400";

  const code = document.createElement("code");
  code.className = "rounded bg-white/5 px-2 py-1";
  code.textContent = item.id;

  codeRow.appendChild(code);

  card.appendChild(header);
  card.appendChild(description);

  if (item.source) {
    const sourceRow = document.createElement("div");
    sourceRow.className = "mt-3 flex items-center gap-2 text-xs text-slate-400";

    sourceRow.appendChild(
      createOutlineSvg(
        "h-4 w-4",
        "M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      )
    );

    const sourceLabel = document.createElement("span");
    sourceLabel.className = "truncate";
    sourceLabel.textContent = item.source;

    sourceRow.appendChild(sourceLabel);
    card.appendChild(sourceRow);
  }

  card.appendChild(codeRow);
  return card;
};

const createItemList = (items) => {
  const container = document.createElement("div");
  container.className = "space-y-3 py-2";
  items.forEach((item) => container.appendChild(createItemCard(item)));
  return container;
};

const createGroupSummary = (level, id, label, countLabel) => {
  const paddingClass = level === 0 ? "p-4" : "p-3";
  const labelClassName =
    level === 0
      ? "text-lg font-semibold text-white"
      : level === 1
        ? "text-base font-semibold text-slate-100"
        : level === 2
          ? "text-sm font-semibold text-slate-200"
          : "text-sm font-medium text-slate-300";
  const iconClassName = level === 0 ? "h-5 w-5" : "h-4 w-4";

  const summary = document.createElement("summary");
  summary.id = id;
  summary.className = `flex cursor-pointer select-none items-center gap-2 ${paddingClass} hover:bg-white/5`;

  summary.appendChild(
    createOutlineSvg(`${iconClassName} items-chevron shrink-0 text-slate-400`, "M9 5l7 7-7 7")
  );

  const labelNode = document.createElement("span");
  labelNode.className = labelClassName;
  labelNode.textContent = label;

  const countNode = document.createElement("span");
  countNode.className = "ml-auto text-xs text-slate-400";
  countNode.textContent = countLabel;

  summary.appendChild(labelNode);
  summary.appendChild(countNode);

  return summary;
};

const renderGroupDetails = (node, level) => {
  const children = getSortedChildren(node);
  const items = [...node.items].sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id));
  const headingId = toGroupDomId(node.path);

  const details = document.createElement("details");
  details.className = "group";
  details.setAttribute("data-group", "");
  details.setAttribute("aria-labelledby", headingId);

  details.appendChild(createGroupSummary(level, headingId, node.label, getCountLabel(node)));

  if (children.length) {
    const container = document.createElement("div");
    container.className = "ml-6 space-y-1 border-l-2 border-slate-800 pl-6";

    children.forEach((child) => {
      container.appendChild(renderGroupDetails(child, level + 1));
    });

    if (items.length) {
      const itemWrap = document.createElement("div");
      itemWrap.className = "pl-6 ml-6";
      itemWrap.appendChild(createItemList(items));
      container.appendChild(itemWrap);
    }

    details.appendChild(container);
  } else if (items.length) {
    const itemWrap = document.createElement("div");
    itemWrap.className = "ml-6 pl-6";
    itemWrap.appendChild(createItemList(items));
    details.appendChild(itemWrap);
  }

  return details;
};

const renderGrouped = (list) => {
  grid.textContent = "";

  const root = buildGroupTree(list);

  const wrapper = document.createElement("div");
  wrapper.className = "overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60";

  const content = document.createElement("div");
  content.className = "space-y-1 py-2";

  if (root.items.length) {
    const ungroupedNode = {
      label: "Ungrouped",
      path: ["ungrouped"],
      children: new Map(),
      items: root.items,
    };
    content.appendChild(renderGroupDetails(ungroupedNode, 0));
  }

  getSortedChildren(root).forEach((child) => {
    content.appendChild(renderGroupDetails(child, 0));
  });

  if (content.childNodes.length) {
    wrapper.appendChild(content);
  } else {
    const empty = document.createElement("div");
    empty.className = "p-4 text-sm text-slate-500";
    empty.textContent = "No items found.";
    wrapper.appendChild(empty);
  }

  grid.appendChild(wrapper);

  count.textContent = String(list.length);
  applyGroupExpansionState();
};

const renderSearchResults = (results) => {
  grid.textContent = "";

  const wrapper = document.createElement("div");
  wrapper.className = "overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/60";

  if (results.length) {
    const content = document.createElement("div");
    content.className = "p-4";
    content.appendChild(createItemList(results.map((result) => result.item)));
    wrapper.appendChild(content);
  } else {
    const empty = document.createElement("div");
    empty.className = "p-4 text-sm text-slate-500";
    empty.textContent = "No items found.";
    wrapper.appendChild(empty);
  }

  grid.appendChild(wrapper);
  count.textContent = String(results.length);
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

    const results = fuse.search(query);
    renderSearchResults(results);
  });
}
