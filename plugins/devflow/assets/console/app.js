const statusLabels = {
  draft: "草稿",
  planning: "规划中",
  plan_approved: "计划已批准",
  developing: "开发中",
  reviewing: "评审中",
  done: "已完成",
};

const reviewVerdictLabels = {
  pass: "通过",
  changes_requested: "要求修改",
  blocked: "阻塞",
};

const artifactOrder = [
  ["summary.md", "Summary"],
  ["request.md", "Request"],
  ["plan.md", "Plan"],
  ["dev.md", "Dev Log"],
  ["change-summary.md", "Change Summary"],
  ["review.md", "Review"],
];

const metricGrid = document.getElementById("metric-grid");
const workspaceListElement = document.getElementById("workspace-list");
const workspaceCountElement = document.getElementById("workspace-count");
const workspaceSummaryElement = document.getElementById("workspace-summary");
const taskListElement = document.getElementById("task-list");
const taskDetailElement = document.getElementById("task-detail");
const tasksHeaderMetaElement = document.getElementById("tasks-header-meta");
const importWorkspaceButton = document.getElementById("import-workspace-button");
const loadExampleButton = document.getElementById("load-example-button");
const clearWorkspacesButton = document.getElementById("clear-workspaces-button");
const workspaceInput = document.getElementById("workspace-input");

const state = {
  workspaces: [],
  selectedWorkspaceId: null,
  selectedTaskId: null,
};

function createId(prefix) {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatStatus(status, isBlocked) {
  if (isBlocked) {
    return "已阻塞";
  }

  return statusLabels[status] || "未知状态";
}

function statusTone(task) {
  if (task.meta.is_blocked) {
    return "blocked";
  }

  return task.meta.status || "idle";
}

function formatVerdict(verdict) {
  return reviewVerdictLabels[verdict] || verdict || "未评审";
}

function formatDate(isoValue) {
  if (!isoValue) {
    return "n/a";
  }

  const date = new Date(isoValue);
  if (Number.isNaN(date.getTime())) {
    return isoValue;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function parseDateValue(isoValue) {
  const timestamp = Date.parse(isoValue || "");
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function compactText(value, maxLength = 220) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "暂无内容。";
  }

  if (text.length <= maxLength) {
    return text;
  }

  return `${text.slice(0, maxLength).trim()}…`;
}

function countStatuses(tasks) {
  const counts = {};

  for (const task of tasks) {
    const key = task.meta.is_blocked ? "blocked" : task.meta.status || "idle";
    counts[key] = (counts[key] || 0) + 1;
  }

  return counts;
}

function sortTasks(tasks, activeTaskId) {
  const statusRank = {
    developing: 0,
    reviewing: 1,
    planning: 2,
    plan_approved: 3,
    draft: 4,
    done: 5,
  };

  return [...tasks].sort((left, right) => {
    const leftActive = left.taskId === activeTaskId ? 1 : 0;
    const rightActive = right.taskId === activeTaskId ? 1 : 0;
    if (leftActive !== rightActive) {
      return rightActive - leftActive;
    }

    const leftBlocked = left.meta.is_blocked ? 1 : 0;
    const rightBlocked = right.meta.is_blocked ? 1 : 0;
    if (leftBlocked !== rightBlocked) {
      return rightBlocked - leftBlocked;
    }

    const leftRank = statusRank[left.meta.status] ?? 9;
    const rightRank = statusRank[right.meta.status] ?? 9;
    if (leftRank !== rightRank) {
      return leftRank - rightRank;
    }

    return parseDateValue(right.meta.updated_at) - parseDateValue(left.meta.updated_at);
  });
}

function createTask(meta, docs, activeTaskId) {
  return {
    taskId: meta.task_id || createId("task"),
    meta,
    docs,
    isActive: meta.task_id === activeTaskId,
  };
}

function buildWorkspace(workspaceInputData) {
  const activeTaskId = workspaceInputData.active?.task_id || null;
  const tasks = sortTasks(
    workspaceInputData.tasks.map((task) => createTask(task.meta, task.docs, activeTaskId)),
    activeTaskId
  );
  const counts = countStatuses(tasks);
  const lastUpdated = tasks.reduce((latest, task) => {
    return Math.max(latest, parseDateValue(task.meta.updated_at));
  }, 0);

  return {
    id: workspaceInputData.id,
    name: workspaceInputData.name,
    sourceLabel: workspaceInputData.sourceLabel,
    sourceType: workspaceInputData.sourceType || "imported",
    description: workspaceInputData.description || "",
    activeTaskId,
    activeStatus: workspaceInputData.active?.status || null,
    tasks,
    counts,
    lastUpdated,
  };
}

function selectedWorkspace() {
  return state.workspaces.find((workspace) => workspace.id === state.selectedWorkspaceId) || null;
}

function selectedTask() {
  const workspace = selectedWorkspace();
  if (!workspace) {
    return null;
  }

  return workspace.tasks.find((task) => task.taskId === state.selectedTaskId) || null;
}

function syncSelection() {
  if (!state.workspaces.length) {
    state.selectedWorkspaceId = null;
    state.selectedTaskId = null;
    return;
  }

  if (!selectedWorkspace()) {
    state.selectedWorkspaceId = state.workspaces[0].id;
  }

  const workspace = selectedWorkspace();
  if (!workspace) {
    state.selectedTaskId = null;
    return;
  }

  const taskStillExists = workspace.tasks.some((task) => task.taskId === state.selectedTaskId);
  if (!taskStillExists) {
    state.selectedTaskId = workspace.activeTaskId || workspace.tasks[0]?.taskId || null;
  }
}

function addWorkspace(workspace) {
  const existingIndex = state.workspaces.findIndex(
    (item) => item.sourceLabel === workspace.sourceLabel && item.name === workspace.name
  );

  if (existingIndex >= 0) {
    state.workspaces.splice(existingIndex, 1, workspace);
  } else {
    state.workspaces.push(workspace);
  }

  state.selectedWorkspaceId = workspace.id;
  state.selectedTaskId = workspace.activeTaskId || workspace.tasks[0]?.taskId || null;
  syncSelection();
  render();
}

function clearAllWorkspaces() {
  state.workspaces = [];
  state.selectedWorkspaceId = null;
  state.selectedTaskId = null;
  render();
}

function removeMarkdownHeading(value) {
  return String(value || "")
    .replace(/^#.*$/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .trim();
}

function renderMetrics() {
  const totalTasks = state.workspaces.reduce((sum, workspace) => sum + workspace.tasks.length, 0);
  const activeTasks = state.workspaces.reduce(
    (sum, workspace) => sum + (workspace.activeTaskId ? 1 : 0),
    0
  );
  const blockedTasks = state.workspaces.reduce(
    (sum, workspace) => sum + (workspace.counts.blocked || 0),
    0
  );
  const inFlightTasks = state.workspaces.reduce((sum, workspace) => {
    return (
      sum +
      (workspace.counts.planning || 0) +
      (workspace.counts.plan_approved || 0) +
      (workspace.counts.developing || 0) +
      (workspace.counts.reviewing || 0)
    );
  }, 0);

  const cards = [
    {
      label: "Workspace 数量",
      value: state.workspaces.length,
      note: "当前页面已导入的独立 DevFlow 工作区。",
    },
    {
      label: "Task 总数",
      value: totalTasks,
      note: "所有已导入 workspace 中识别到的任务数量。",
    },
    {
      label: "进行中",
      value: inFlightTasks,
      note: "状态为 planning / approved / developing / reviewing 的任务。",
    },
    {
      label: "当前活动 Task",
      value: activeTasks,
      note: blockedTasks ? `其中 ${blockedTasks} 个处于 blocked。` : "当前没有 blocked task。",
    },
  ];

  metricGrid.innerHTML = cards
    .map((card) => {
      return `
        <article class="metric-card">
          <div class="metric-label">${escapeHtml(card.label)}</div>
          <div class="metric-value">${escapeHtml(card.value)}</div>
          <div class="metric-note">${escapeHtml(card.note)}</div>
        </article>
      `;
    })
    .join("");
}

function renderWorkspaceList() {
  workspaceCountElement.textContent = String(state.workspaces.length);

  if (!state.workspaces.length) {
    workspaceListElement.innerHTML = `
      <div class="empty-state">
        还没有导入任何 workspace。
        <br />
        点击“导入 Workspace”读取本地目录，或先用“载入示例”看看界面结构。
      </div>
    `;
    return;
  }

  workspaceListElement.innerHTML = state.workspaces
    .map((workspace) => {
      const isSelected = workspace.id === state.selectedWorkspaceId;
      const activeTask = workspace.tasks.find((task) => task.taskId === workspace.activeTaskId) || null;
      const chips = [
        workspace.activeTaskId
          ? `<span class="mini-badge" data-tone="accent">当前任务 ${escapeHtml(workspace.activeTaskId)}</span>`
          : `<span class="mini-badge" data-tone="neutral">无当前任务</span>`,
        `<span class="mini-badge" data-tone="neutral">${escapeHtml(workspace.tasks.length)} tasks</span>`,
        workspace.counts.blocked
          ? `<span class="mini-badge" data-tone="danger">${escapeHtml(
              workspace.counts.blocked
            )} blocked</span>`
          : "",
      ]
        .filter(Boolean)
        .join("");

      return `
        <article class="workspace-card ${isSelected ? "is-selected" : ""}" data-workspace-id="${escapeHtml(
          workspace.id
        )}">
          <div class="workspace-card-header">
            <div>
              <h3 class="workspace-title">${escapeHtml(workspace.name)}</h3>
              <div class="workspace-path">${escapeHtml(workspace.sourceLabel)}</div>
            </div>
            <span class="status-badge" data-tone="${escapeHtml(
              activeTask ? statusTone(activeTask) : "idle"
            )}">${escapeHtml(
              activeTask ? formatStatus(activeTask.meta.status, activeTask.meta.is_blocked) : "空闲"
            )}</span>
          </div>
          <p class="workspace-description">${escapeHtml(
            workspace.description ||
              (activeTask
                ? `当前 task: ${activeTask.meta.title || activeTask.taskId}`
                : "这个 workspace 目前没有 active task。")
          )}</p>
          <div class="workspace-meta">${chips}</div>
        </article>
      `;
    })
    .join("");
}

function renderWorkspaceSummary() {
  const workspace = selectedWorkspace();

  if (!workspace) {
    tasksHeaderMetaElement.innerHTML = "";
    workspaceSummaryElement.innerHTML = `
      <div class="empty-state">
        请选择一个 workspace。导入后这里会显示该 workspace 的当前 task、状态概览和更新时间。
      </div>
    `;
    return;
  }

  const activeTask = workspace.tasks.find((task) => task.taskId === workspace.activeTaskId) || null;
  const latestLabel = workspace.lastUpdated ? formatDate(workspace.lastUpdated) : "n/a";

  tasksHeaderMetaElement.innerHTML = `
    <span class="count-badge">${escapeHtml(workspace.sourceType === "sample" ? "示例数据" : "本地目录")}</span>
    <span>${escapeHtml(workspace.tasks.length)} tasks</span>
    <span>最近更新 ${escapeHtml(latestLabel)}</span>
  `;

  const chips = [
    workspace.counts.planning
      ? `<span class="mini-badge" data-tone="warn">${escapeHtml(workspace.counts.planning)} planning</span>`
      : "",
    workspace.counts.plan_approved
      ? `<span class="mini-badge" data-tone="warn">${escapeHtml(
          workspace.counts.plan_approved
        )} approved</span>`
      : "",
    workspace.counts.developing
      ? `<span class="mini-badge" data-tone="accent">${escapeHtml(
          workspace.counts.developing
        )} developing</span>`
      : "",
    workspace.counts.reviewing
      ? `<span class="mini-badge" data-tone="warn">${escapeHtml(
          workspace.counts.reviewing
        )} reviewing</span>`
      : "",
    workspace.counts.done
      ? `<span class="mini-badge" data-tone="neutral">${escapeHtml(workspace.counts.done)} done</span>`
      : "",
    workspace.counts.blocked
      ? `<span class="mini-badge" data-tone="danger">${escapeHtml(
          workspace.counts.blocked
        )} blocked</span>`
      : "",
  ]
    .filter(Boolean)
    .join("");

  workspaceSummaryElement.innerHTML = `
    <div class="summary-top">
      <article class="summary-card">
        <div class="summary-card-header">
          <div>
            <h3 class="summary-title">${escapeHtml(workspace.name)}</h3>
            <div class="workspace-path">${escapeHtml(workspace.sourceLabel)}</div>
          </div>
          <span class="status-badge" data-tone="${escapeHtml(
            activeTask ? statusTone(activeTask) : "idle"
          )}">${escapeHtml(
            activeTask ? formatStatus(activeTask.meta.status, activeTask.meta.is_blocked) : "无当前任务"
          )}</span>
        </div>
        <p class="summary-copy">${escapeHtml(
          activeTask
            ? `${activeTask.taskId} · ${activeTask.meta.title || "未命名任务"}`
            : "当前 active-task.json 中没有指向活动任务。"
        )}</p>
        <div class="summary-chip-row">${chips || '<span class="mini-badge" data-tone="neutral">暂无状态分布</span>'}</div>
      </article>

      <article class="summary-card">
        <div class="summary-stats">
          <div class="summary-stat">
            <strong>${escapeHtml(workspace.tasks.length)}</strong>
            <span>任务总数</span>
          </div>
          <div class="summary-stat">
            <strong>${escapeHtml(workspace.activeTaskId || "0")}</strong>
            <span>当前任务 ID</span>
          </div>
          <div class="summary-stat">
            <strong>${escapeHtml(workspace.counts.done || 0)}</strong>
            <span>已完成</span>
          </div>
          <div class="summary-stat">
            <strong>${escapeHtml(workspace.counts.blocked || 0)}</strong>
            <span>阻塞中</span>
          </div>
        </div>
      </article>
    </div>

    <div class="info-grid">
      <div class="info-cell">
        <span class="info-label">Current Task</span>
        <span class="info-value">${escapeHtml(activeTask?.meta.title || activeTask?.taskId || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Current Step</span>
        <span class="info-value">${escapeHtml(activeTask?.meta.current_step || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Next Action</span>
        <span class="info-value">${escapeHtml(activeTask?.meta.next_action || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Last Updated</span>
        <span class="info-value">${escapeHtml(latestLabel)}</span>
      </div>
    </div>
  `;
}

function renderTaskList() {
  const workspace = selectedWorkspace();

  if (!workspace) {
    taskListElement.innerHTML = `
      <div class="empty-state">
        导入 workspace 后，这里会列出该目录下 <code>tasks/*/meta.json</code> 对应的所有任务。
      </div>
    `;
    return;
  }

  if (!workspace.tasks.length) {
    taskListElement.innerHTML = `
      <div class="empty-state">
        这个 workspace 没有识别到任何任务。
      </div>
    `;
    return;
  }

  taskListElement.innerHTML = workspace.tasks
    .map((task) => {
      const selected = task.taskId === state.selectedTaskId;
      const subtitle =
        task.meta.current_step || task.meta.last_completed_step || task.meta.next_action || "暂无进展描述";
      const requestSnippet = compactText(removeMarkdownHeading(task.docs["request.md"]), 140);

      return `
        <article class="task-card ${selected ? "is-selected" : ""}" data-task-id="${escapeHtml(
          task.taskId
        )}">
          <div class="task-card-header">
            <div>
              <h3 class="task-title">${escapeHtml(task.taskId)}</h3>
              <p class="task-subline">${escapeHtml(task.meta.title || "未命名任务")}</p>
            </div>
            <span class="status-badge" data-tone="${escapeHtml(statusTone(task))}">
              ${escapeHtml(formatStatus(task.meta.status, task.meta.is_blocked))}
            </span>
          </div>
          <div class="task-card-body">
            <p class="task-subline">${escapeHtml(subtitle)}</p>
            <p class="task-subline">${escapeHtml(requestSnippet)}</p>
            <div class="task-meta">
              ${
                task.isActive
                  ? '<span class="mini-badge" data-tone="accent">当前 task</span>'
                  : ""
              }
              <span class="mini-badge" data-tone="neutral">plan v${escapeHtml(
                task.meta.plan_version ?? "n/a"
              )}</span>
              <span class="mini-badge" data-tone="neutral">review ${escapeHtml(
                task.meta.review_round ?? 0
              )}</span>
              ${
                task.meta.next_action
                  ? `<span class="mini-badge" data-tone="warn">${escapeHtml(task.meta.next_action)}</span>`
                  : ""
              }
              <span class="mini-badge" data-tone="${
                task.meta.is_blocked ? "danger" : "neutral"
              }">${escapeHtml(formatDate(task.meta.updated_at))}</span>
            </div>
          </div>
        </article>
      `;
    })
    .join("");
}

function renderTaskDetail() {
  const workspace = selectedWorkspace();
  const task = selectedTask();

  if (!workspace || !task) {
    taskDetailElement.innerHTML = `
      <div class="empty-state">
        选择一个 task 后，这里会显示 <code>meta.json</code> 关键字段和主要文档摘要。
      </div>
    `;
    return;
  }

  const detailChips = [
    task.isActive ? '<span class="mini-badge" data-tone="accent">当前 task</span>' : "",
    task.meta.next_action
      ? `<span class="mini-badge" data-tone="warn">next: ${escapeHtml(task.meta.next_action)}</span>`
      : "",
    task.meta.last_review_verdict
      ? `<span class="mini-badge" data-tone="${
          task.meta.last_review_verdict === "pass" ? "accent" : "danger"
        }">review: ${escapeHtml(formatVerdict(task.meta.last_review_verdict))}</span>`
      : "",
    task.meta.is_blocked
      ? `<span class="mini-badge" data-tone="danger">${escapeHtml(
          task.meta.block_reason || "blocked"
        )}</span>`
      : "",
  ]
    .filter(Boolean)
    .join("");

  const artifacts = artifactOrder
    .map(([fileName, label]) => {
      const content = task.docs[fileName];
      if (!content) {
        return "";
      }

      return `
        <article class="artifact-card">
          <p class="artifact-label">${escapeHtml(label)}</p>
          <h3 class="artifact-title">${escapeHtml(fileName)}</h3>
          <p class="artifact-content">${escapeHtml(
            compactText(removeMarkdownHeading(content), 380)
          )}</p>
        </article>
      `;
    })
    .filter(Boolean)
    .join("");

  taskDetailElement.innerHTML = `
    <article class="summary-card">
      <div class="summary-card-header">
        <div>
          <h3 class="summary-title">${escapeHtml(task.meta.title || task.taskId)}</h3>
          <div class="workspace-path">${escapeHtml(workspace.name)} / ${escapeHtml(task.taskId)}</div>
        </div>
        <span class="status-badge" data-tone="${escapeHtml(statusTone(task))}">
          ${escapeHtml(formatStatus(task.meta.status, task.meta.is_blocked))}
        </span>
      </div>
      <div class="detail-chip-row">${detailChips || '<span class="mini-badge" data-tone="neutral">无额外标记</span>'}</div>
    </article>

    <div class="info-grid">
      <div class="info-cell">
        <span class="info-label">Current Step</span>
        <span class="info-value">${escapeHtml(task.meta.current_step || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Last Completed</span>
        <span class="info-value">${escapeHtml(task.meta.last_completed_step || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Plan Version</span>
        <span class="info-value">${escapeHtml(task.meta.plan_version ?? "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Review Round</span>
        <span class="info-value">${escapeHtml(task.meta.review_round ?? "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Created At</span>
        <span class="info-value">${escapeHtml(formatDate(task.meta.created_at))}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Updated At</span>
        <span class="info-value">${escapeHtml(formatDate(task.meta.updated_at))}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Approved At</span>
        <span class="info-value">${escapeHtml(formatDate(task.meta.approved_at))}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Completed At</span>
        <span class="info-value">${escapeHtml(formatDate(task.meta.completed_at))}</span>
      </div>
    </div>

    ${artifacts || '<div class="empty-state">这个 task 还没有可展示的文档摘要。</div>'}
  `;
}

function render() {
  syncSelection();
  renderMetrics();
  renderWorkspaceList();
  renderWorkspaceSummary();
  renderTaskList();
  renderTaskDetail();
}

async function readJsonFile(file, fileLabel) {
  try {
    return JSON.parse(await file.text());
  } catch (error) {
    throw new Error(`无法解析 ${fileLabel}: ${error.message}`);
  }
}

async function readTextFile(file) {
  return file ? file.text() : "";
}

function findWorkspaceRootPrefix(files) {
  const prefixes = new Set();

  for (const file of files) {
    const parts = String(file.webkitRelativePath || "")
      .split("/")
      .filter(Boolean);
    const workspaceIndex = parts.indexOf("DevFlowWorkspace");
    if (workspaceIndex >= 0) {
      prefixes.add(parts.slice(0, workspaceIndex + 1).join("/"));
    }
  }

  if (!prefixes.size) {
    throw new Error("没有在所选目录中找到 DevFlowWorkspace。");
  }

  if (prefixes.size > 1) {
    throw new Error("一次导入请只选择一个包含 DevFlowWorkspace 的目录。");
  }

  return [...prefixes][0];
}

function collectWorkspaceFiles(files, prefix) {
  const fileMap = new Map();

  for (const file of files) {
    const relativePath = String(file.webkitRelativePath || "");
    if (!relativePath.startsWith(`${prefix}/`)) {
      continue;
    }

    const workspaceRelativePath = relativePath.slice(prefix.length + 1);
    fileMap.set(workspaceRelativePath, file);
  }

  return fileMap;
}

function deriveWorkspaceName(prefix) {
  const parts = prefix.split("/").filter(Boolean);
  if (parts.at(-1) === "DevFlowWorkspace" && parts.length > 1) {
    return parts.at(-2);
  }

  return parts.at(-1) || "Workspace";
}

async function parseImportedWorkspace(files) {
  const prefix = findWorkspaceRootPrefix(files);
  const fileMap = collectWorkspaceFiles(files, prefix);
  const activeTaskFile = fileMap.get("active-task.json");

  if (!activeTaskFile) {
    throw new Error("所选目录缺少 active-task.json。");
  }

  const active = await readJsonFile(activeTaskFile, "active-task.json");
  const metaEntries = [...fileMap.entries()].filter(([path]) => /^tasks\/[^/]+\/meta\.json$/.test(path));

  if (!metaEntries.length) {
    throw new Error("所选 workspace 中没有找到 tasks/*/meta.json。");
  }

  const tasks = await Promise.all(
    metaEntries.map(async ([path, file]) => {
      const taskId = path.split("/")[1];
      const docs = Object.fromEntries(
        await Promise.all(
          artifactOrder.map(async ([fileName]) => {
            const docPath = `tasks/${taskId}/${fileName}`;
            return [fileName, await readTextFile(fileMap.get(docPath))];
          })
        )
      );

      return {
        meta: await readJsonFile(file, path),
        docs,
      };
    })
  );

  return buildWorkspace({
    id: createId("workspace"),
    name: deriveWorkspaceName(prefix),
    sourceLabel: prefix,
    sourceType: "imported",
    description: "从本地目录导入的 DevFlowWorkspace。",
    active,
    tasks,
  });
}

async function handleWorkspaceImport(event) {
  const files = [...(event.target.files || [])];
  workspaceInput.value = "";

  if (!files.length) {
    return;
  }

  try {
    const workspace = await parseImportedWorkspace(files);
    addWorkspace(workspace);
  } catch (error) {
    window.alert(error.message);
  }
}

function createExampleWorkspaces() {
  const exampleA = buildWorkspace({
    id: "sample-workspace-alpha",
    name: "alpha-repo",
    sourceLabel: "alpha-repo/DevFlowWorkspace",
    sourceType: "sample",
    description: "一个包含规划中、开发中和已完成任务的示例 workspace。",
    active: {
      task_id: "TASK-008",
      title: "实现 DevFlow dashboard",
      task_dir: "tasks/TASK-008",
      status: "developing",
    },
    tasks: [
      {
        meta: {
          task_id: "TASK-008",
          title: "实现 DevFlow dashboard",
          status: "developing",
          created_at: "2026-04-14T08:00:00+08:00",
          updated_at: "2026-04-14T10:20:00+08:00",
          plan_version: 3,
          review_round: 1,
          current_step: "build browser-side workspace loader",
          last_completed_step: "confirm data model",
          next_action: "review",
          is_blocked: false,
          block_reason: null,
          approved_at: "2026-04-14T08:40:00+08:00",
          last_review_verdict: "changes_requested",
          completed_at: null,
        },
        docs: {
          "request.md":
            "# Request\n\n给 devflow 做一个管理界面，支持同时打开多个 DevFlowWorkspace 并查看 task 状态。",
          "plan.md":
            "# Plan\n\n先做纯前端管理台，再补导入目录、task 详情和多 workspace 切换。",
          "dev.md":
            "# Dev\n\n已完成 dashboard 骨架、多栏布局和 workspace 解析逻辑。",
          "change-summary.md":
            "# Change Summary\n\n替换旧 demo 页面，新增 workspace 导入、任务列表和详情区。",
          "review.md":
            "# Review\n\n上一轮评审要求补充多 workspace 体验与状态总览。",
          "summary.md":
            "# Summary\n\n正在开发 DevFlow 管理界面，当前主要集中在浏览器侧的数据导入和展示。",
        },
      },
      {
        meta: {
          task_id: "TASK-007",
          title: "设计统一 task 卡片",
          status: "planning",
          created_at: "2026-04-14T07:10:00+08:00",
          updated_at: "2026-04-14T08:30:00+08:00",
          plan_version: 1,
          review_round: 0,
          current_step: "draft initial plan",
          last_completed_step: null,
          next_action: "approve-plan",
          is_blocked: false,
          block_reason: null,
          approved_at: null,
          last_review_verdict: null,
          completed_at: null,
        },
        docs: {
          "request.md":
            "# Request\n\n整理任务卡片展示字段，统一状态、时间和当前步骤的排布。",
          "plan.md":
            "# Plan\n\n对比现有 meta.json 字段，给卡片设计固定信息层级。",
          "summary.md": "# Summary\n\n仍在规划阶段，等待 plan 批准。",
        },
      },
      {
        meta: {
          task_id: "TASK-006",
          title: "把示例页面替换成控制台",
          status: "done",
          created_at: "2026-04-13T18:10:00+08:00",
          updated_at: "2026-04-13T22:30:00+08:00",
          plan_version: 2,
          review_round: 1,
          current_step: "review passed",
          last_completed_step: "review pass",
          next_action: null,
          is_blocked: false,
          block_reason: null,
          approved_at: "2026-04-13T19:00:00+08:00",
          last_review_verdict: "pass",
          completed_at: "2026-04-13T22:30:00+08:00",
        },
        docs: {
          "summary.md": "# Summary\n\n旧的游戏 demo 已经被新的 DevFlow 控制台取代。",
          "review.md": "# Review\n\n界面结构清晰，已通过。",
        },
      },
    ],
  });

  const exampleB = buildWorkspace({
    id: "sample-workspace-beta",
    name: "release-train",
    sourceLabel: "release-train/DevFlowWorkspace",
    sourceType: "sample",
    description: "一个包含 blocked、reviewing 和 approved 状态的示例 workspace。",
    active: {
      task_id: "TASK-014",
      title: "评审插件市场同步逻辑",
      task_dir: "tasks/TASK-014",
      status: "reviewing",
    },
    tasks: [
      {
        meta: {
          task_id: "TASK-014",
          title: "评审插件市场同步逻辑",
          status: "reviewing",
          created_at: "2026-04-14T06:50:00+08:00",
          updated_at: "2026-04-14T09:40:00+08:00",
          plan_version: 2,
          review_round: 2,
          current_step: "wait for reviewer verdict",
          last_completed_step: "generate change summary",
          next_action: "await_review_result",
          is_blocked: false,
          block_reason: null,
          approved_at: "2026-04-14T07:12:00+08:00",
          last_review_verdict: "pass",
          completed_at: null,
        },
        docs: {
          "request.md":
            "# Request\n\n检查 marketplace.json 的同步脚本是否覆盖新增 repo-local 插件路径。",
          "change-summary.md":
            "# Change Summary\n\n本轮变更主要覆盖 marketplace 读取、排序和状态显示。",
          "review.md":
            "# Review\n\n当前进入 reviewing，等待最终 verdict。",
        },
      },
      {
        meta: {
          task_id: "TASK-013",
          title: "修复 workspace 解析异常",
          status: "developing",
          created_at: "2026-04-14T05:40:00+08:00",
          updated_at: "2026-04-14T08:55:00+08:00",
          plan_version: 4,
          review_round: 1,
          current_step: "investigate malformed meta payload",
          last_completed_step: "collect failing examples",
          next_action: "dev",
          is_blocked: true,
          block_reason: "等待用户提供损坏样例",
          approved_at: "2026-04-14T06:10:00+08:00",
          last_review_verdict: "blocked",
          completed_at: null,
        },
        docs: {
          "request.md": "# Request\n\n某些 workspace 无法读出 meta.json，需要明确错误提示。",
          "dev.md": "# Dev\n\n已定位到 JSON 解析失败，但还缺具体损坏样例。",
          "summary.md": "# Summary\n\n任务暂时 blocked，等样例后继续。",
        },
      },
      {
        meta: {
          task_id: "TASK-012",
          title: "整理 workspace 总览指标",
          status: "plan_approved",
          created_at: "2026-04-14T04:20:00+08:00",
          updated_at: "2026-04-14T05:15:00+08:00",
          plan_version: 2,
          review_round: 0,
          current_step: "plan approved",
          last_completed_step: "user approved plan",
          next_action: "dev",
          is_blocked: false,
          block_reason: null,
          approved_at: "2026-04-14T05:15:00+08:00",
          last_review_verdict: null,
          completed_at: null,
        },
        docs: {
          "plan.md": "# Plan\n\n统计 workspace 数量、active task 数量、进行中任务和 blocked task。",
          "summary.md": "# Summary\n\n计划已批准，等待开发。",
        },
      },
    ],
  });

  return [exampleA, exampleB];
}

function loadExampleWorkspaces() {
  for (const workspace of createExampleWorkspaces()) {
    addWorkspace(workspace);
  }
}

workspaceListElement.addEventListener("click", (event) => {
  const card = event.target.closest("[data-workspace-id]");
  if (!card) {
    return;
  }

  state.selectedWorkspaceId = card.dataset.workspaceId;
  state.selectedTaskId = null;
  render();
});

taskListElement.addEventListener("click", (event) => {
  const card = event.target.closest("[data-task-id]");
  if (!card) {
    return;
  }

  state.selectedTaskId = card.dataset.taskId;
  render();
});

importWorkspaceButton.addEventListener("click", () => {
  workspaceInput.click();
});

workspaceInput.addEventListener("change", handleWorkspaceImport);

loadExampleButton.addEventListener("click", () => {
  loadExampleWorkspaces();
});

clearWorkspacesButton.addEventListener("click", () => {
  clearAllWorkspaces();
});

render();
