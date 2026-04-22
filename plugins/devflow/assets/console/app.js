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
  ["summary.md", "Task Summary"],
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

function removeMarkdownHeading(value) {
  return String(value || "")
    .replace(/^#.*$/gm, "")
    .replace(/^[-*]\s+/gm, "")
    .replace(/^\d+\.\s+/gm, "")
    .trim();
}

function countStatuses(tasks) {
  const counts = {};

  for (const task of tasks) {
    const key = task.meta.is_blocked ? "blocked" : task.meta.status || "idle";
    counts[key] = (counts[key] || 0) + 1;
  }

  return counts;
}

function sortTasks(tasks, focusTaskId) {
  const statusRank = {
    developing: 0,
    reviewing: 1,
    planning: 2,
    plan_approved: 3,
    draft: 4,
    done: 5,
  };

  return [...tasks].sort((left, right) => {
    const leftFocus = left.taskId === focusTaskId ? 1 : 0;
    const rightFocus = right.taskId === focusTaskId ? 1 : 0;
    if (leftFocus !== rightFocus) {
      return rightFocus - leftFocus;
    }

    const leftActive = left.isActive ? 1 : 0;
    const rightActive = right.isActive ? 1 : 0;
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

function normalizeActiveIndex(activeTasks, active) {
  if (activeTasks && Array.isArray(activeTasks.tasks)) {
    return {
      focus_task_id: activeTasks.focus_task_id || null,
      tasks: activeTasks.tasks,
    };
  }

  if (active && active.task_id) {
    return {
      focus_task_id: active.task_id,
      tasks: [
        {
          task_id: active.task_id,
          title: active.title || null,
          task_dir: active.task_dir || null,
          status: active.status || null,
          is_blocked: false,
          worktree_path: null,
          updated_at: null,
        },
      ],
    };
  }

  return {
    focus_task_id: null,
    tasks: [],
  };
}

function defaultGlobalSummary() {
  return {
    updated_at: null,
    focus_task_id: null,
    active_task_count: 0,
    done_task_count: 0,
    tasks: [],
  };
}

function createTask(meta, docs, focusTaskId, activeTaskIds) {
  return {
    taskId: meta.task_id || createId("task"),
    meta,
    docs,
    isFocus: meta.task_id === focusTaskId,
    isActive: activeTaskIds.has(meta.task_id),
  };
}

function buildWorkspace(workspaceInputData) {
  const activeIndex = normalizeActiveIndex(workspaceInputData.activeTasks, workspaceInputData.active);
  const focusTaskId = activeIndex.focus_task_id || null;
  const activeTaskIds = new Set(activeIndex.tasks.map((task) => task.task_id));
  const tasks = sortTasks(
    workspaceInputData.tasks.map((task) => createTask(task.meta, task.docs, focusTaskId, activeTaskIds)),
    focusTaskId
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
    focusTaskId,
    activeCount: activeIndex.tasks.length,
    activeIndex,
    tasks,
    counts,
    lastUpdated,
    globalSummary: workspaceInputData.globalSummary || defaultGlobalSummary(),
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
    state.selectedTaskId = workspace.focusTaskId || workspace.tasks[0]?.taskId || null;
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
  state.selectedTaskId = workspace.focusTaskId || workspace.tasks[0]?.taskId || null;
  syncSelection();
  render();
}

function clearAllWorkspaces() {
  state.workspaces = [];
  state.selectedWorkspaceId = null;
  state.selectedTaskId = null;
  render();
}

function activeTaskEntry(workspace) {
  return workspace.tasks.find((task) => task.taskId === workspace.focusTaskId) || null;
}

function globalTaskSummary(workspace, taskId) {
  return (
    workspace.globalSummary.tasks.find((task) => task.task_id === taskId) || {
      overview: "暂无全局摘要。",
      key_structures: [],
      key_config: [],
      pitfalls: [],
      cross_task_notes: [],
    }
  );
}

function renderBulletList(items, emptyText) {
  if (!items?.length) {
    return `<p class="artifact-content">${escapeHtml(emptyText)}</p>`;
  }

  return `
    <div class="summary-chip-row">
      ${items
        .map((item) => `<span class="mini-badge" data-tone="neutral">${escapeHtml(compactText(item, 120))}</span>`)
        .join("")}
    </div>
  `;
}

function renderMetrics() {
  const totalTasks = state.workspaces.reduce((sum, workspace) => sum + workspace.tasks.length, 0);
  const activeTasks = state.workspaces.reduce((sum, workspace) => sum + workspace.activeCount, 0);
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
      label: "活跃 Task",
      value: activeTasks,
      note: "来自 active-tasks.json 的未完成任务索引总数。",
    },
    {
      label: "进行中 / 阻塞",
      value: `${inFlightTasks} / ${blockedTasks}`,
      note: "便于快速识别需要协调和排障的任务。",
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
        点击“导入 Workspace”读取本地目录，或先用“载入示例”看看多 task 视图。
      </div>
    `;
    return;
  }

  workspaceListElement.innerHTML = state.workspaces
    .map((workspace) => {
      const isSelected = workspace.id === state.selectedWorkspaceId;
      const focusTask = activeTaskEntry(workspace);
      const chips = [
        workspace.focusTaskId
          ? `<span class="mini-badge" data-tone="accent">焦点 ${escapeHtml(workspace.focusTaskId)}</span>`
          : `<span class="mini-badge" data-tone="neutral">无焦点 task</span>`,
        `<span class="mini-badge" data-tone="neutral">${escapeHtml(workspace.activeCount)} active</span>`,
        workspace.counts.blocked
          ? `<span class="mini-badge" data-tone="danger">${escapeHtml(
              workspace.counts.blocked
            )} blocked</span>`
          : "",
        workspace.globalSummary.updated_at
          ? `<span class="mini-badge" data-tone="warn">summary ${escapeHtml(
              formatDate(workspace.globalSummary.updated_at)
            )}</span>`
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
              focusTask ? statusTone(focusTask) : "idle"
            )}">${escapeHtml(
              focusTask ? formatStatus(focusTask.meta.status, focusTask.meta.is_blocked) : "空闲"
            )}</span>
          </div>
          <p class="workspace-description">${escapeHtml(
            workspace.description ||
              (focusTask
                ? `焦点 task: ${focusTask.meta.title || focusTask.taskId}`
                : "这个 workspace 当前没有 focus task。")
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
        请选择一个 workspace。导入后这里会显示 focus task、多 task 状态和全局 summary 摘要。
      </div>
    `;
    return;
  }

  const focusTask = activeTaskEntry(workspace);
  const latestLabel = workspace.lastUpdated ? formatDate(workspace.lastUpdated) : "n/a";
  const globalSummary = workspace.globalSummary;

  tasksHeaderMetaElement.innerHTML = `
    <span class="count-badge">${escapeHtml(workspace.sourceType === "sample" ? "示例数据" : "本地目录")}</span>
    <span>${escapeHtml(workspace.activeCount)} active</span>
    <span>焦点 ${escapeHtml(workspace.focusTaskId || "n/a")}</span>
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
            focusTask ? statusTone(focusTask) : "idle"
          )}">${escapeHtml(
            focusTask ? formatStatus(focusTask.meta.status, focusTask.meta.is_blocked) : "无焦点 task"
          )}</span>
        </div>
        <p class="summary-copy">${escapeHtml(
          focusTask
            ? `${focusTask.taskId} · ${focusTask.meta.title || "未命名任务"}`
            : "当前 active-tasks.json 没有记录 focus task。"
        )}</p>
        <div class="summary-chip-row">${chips || '<span class="mini-badge" data-tone="neutral">暂无状态分布</span>'}</div>
      </article>

      <article class="summary-card">
        <div class="summary-card-header">
          <div>
            <h3 class="summary-title">Global Summary</h3>
            <div class="workspace-path">${escapeHtml(formatDate(globalSummary.updated_at))}</div>
          </div>
          <span class="count-badge">${escapeHtml(globalSummary.active_task_count || 0)} active</span>
        </div>
        <p class="summary-copy">${escapeHtml(
          compactText(
            focusTask ? globalTaskSummary(workspace, focusTask.taskId).overview : "暂无焦点 task 对应的全局摘要。",
            180
          )
        )}</p>
        <div class="summary-chip-row">
          <span class="mini-badge" data-tone="accent">focus ${escapeHtml(globalSummary.focus_task_id || "n/a")}</span>
          <span class="mini-badge" data-tone="neutral">${escapeHtml(globalSummary.done_task_count || 0)} done</span>
        </div>
      </article>
    </div>

    <div class="info-grid">
      <div class="info-cell">
        <span class="info-label">Focus Task</span>
        <span class="info-value">${escapeHtml(focusTask?.meta.title || focusTask?.taskId || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Stage Status</span>
        <span class="info-value">${escapeHtml(focusTask ? formatStatus(focusTask.meta.status, focusTask.meta.is_blocked) : "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Next Action</span>
        <span class="info-value">${escapeHtml(focusTask?.meta.next_action || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Global Summary Updated</span>
        <span class="info-value">${escapeHtml(formatDate(globalSummary.updated_at))}</span>
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
                task.isFocus
                  ? '<span class="mini-badge" data-tone="accent">焦点 task</span>'
                  : ""
              }
              ${
                task.isActive && !task.isFocus
                  ? '<span class="mini-badge" data-tone="warn">并行 active</span>'
                  : ""
              }
              <span class="mini-badge" data-tone="neutral">plan v${escapeHtml(
                task.meta.plan_version ?? "n/a"
              )}</span>
              <span class="mini-badge" data-tone="neutral">review ${escapeHtml(
                task.meta.review_round ?? 0
              )}</span>
              ${
                task.meta.execution_mode === "auto_dev"
                  ? `<span class="mini-badge" data-tone="${
                      task.meta.auto_loop_state === "blocked" ? "danger" : "accent"
                    }">auto-dev${task.meta.auto_loop_state ? `:${escapeHtml(task.meta.auto_loop_state)}` : ""}</span>`
                  : ""
              }
              ${
                task.meta.active_subagent_role
                  ? `<span class="mini-badge" data-tone="warn">${escapeHtml(
                      `${task.meta.active_subagent_role}:${task.meta.active_subagent_run_id || "pending"}`
                    )}</span>`
                  : ""
              }
              ${
                task.meta.worktree_branch
                  ? `<span class="mini-badge" data-tone="neutral">${escapeHtml(task.meta.worktree_branch)}</span>`
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
        选择一个 task 后，这里会显示 <code>meta.json</code>、worktree 和 global summary 里的关键信息。
      </div>
    `;
    return;
  }

  const globalTask = globalTaskSummary(workspace, task.taskId);
  const detailChips = [
    task.isFocus ? '<span class="mini-badge" data-tone="accent">焦点 task</span>' : "",
    task.isActive && !task.isFocus ? '<span class="mini-badge" data-tone="warn">并行 active</span>' : "",
    task.meta.next_action
      ? `<span class="mini-badge" data-tone="warn">next: ${escapeHtml(task.meta.next_action)}</span>`
      : "",
    task.meta.execution_mode === "auto_dev"
      ? `<span class="mini-badge" data-tone="${
          task.meta.auto_loop_state === "blocked" ? "danger" : "accent"
        }">auto-dev: ${escapeHtml(task.meta.auto_loop_state || "running")}</span>`
      : "",
    task.meta.execution_mode === "auto_dev" && task.meta.auto_loop_state === "running"
      ? `<span class="mini-badge" data-tone="neutral">auto-next: ${escapeHtml(
          task.meta.next_action === "review" ? "review" : task.meta.status === "reviewing" ? "await_review_result" : "dev"
        )}</span>`
      : "",
    task.meta.last_review_verdict
      ? `<span class="mini-badge" data-tone="${
          task.meta.last_review_verdict === "pass" ? "accent" : "danger"
        }">review: ${escapeHtml(formatVerdict(task.meta.last_review_verdict))}</span>`
      : "",
    task.meta.active_subagent_role
      ? `<span class="mini-badge" data-tone="warn">${escapeHtml(
          `active: ${task.meta.active_subagent_role}/${task.meta.active_subagent_run_id || "pending"}`
        )}</span>`
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
        <span class="info-label">Stage Status</span>
        <span class="info-value">${escapeHtml(task.meta.status || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Current Step</span>
        <span class="info-value">${escapeHtml(task.meta.current_step || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Next Action</span>
        <span class="info-value">${escapeHtml(task.meta.next_action || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Execution Mode</span>
        <span class="info-value">${escapeHtml(task.meta.execution_mode || "manual")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Auto Loop State</span>
        <span class="info-value">${escapeHtml(task.meta.auto_loop_state || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Blocked</span>
        <span class="info-value">${escapeHtml(task.meta.is_blocked ? task.meta.block_reason || "yes" : "no")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Worktree Path</span>
        <span class="info-value">${escapeHtml(task.meta.worktree_path || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Worktree Branch</span>
        <span class="info-value">${escapeHtml(task.meta.worktree_branch || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Worktree Base Ref</span>
        <span class="info-value">${escapeHtml(task.meta.worktree_base_ref || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Global Summary Sync</span>
        <span class="info-value">${escapeHtml(formatDate(task.meta.global_summary_updated_at))}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Active Subagent</span>
        <span class="info-value">${escapeHtml(task.meta.active_subagent_role || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Active Run ID</span>
        <span class="info-value">${escapeHtml(task.meta.active_subagent_run_id || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Active Status</span>
        <span class="info-value">${escapeHtml(task.meta.active_subagent_status || "n/a")}</span>
      </div>
      <div class="info-cell">
        <span class="info-label">Active Result Path</span>
        <span class="info-value">${escapeHtml(task.meta.active_subagent_result_path || "n/a")}</span>
      </div>
    </div>

    <article class="artifact-card">
      <p class="artifact-label">GLOBAL KNOWLEDGE</p>
      <h3 class="artifact-title">Shared Notes For Other Tasks</h3>
      <p class="artifact-content">${escapeHtml(globalTask.overview || "暂无全局摘要。")}</p>
      <p class="artifact-label">Structures / Interfaces / File Contracts</p>
      ${renderBulletList(globalTask.key_structures, "暂无明确记录。")}
      <p class="artifact-label">Config / Environment</p>
      ${renderBulletList(globalTask.key_config, "暂无明确记录。")}
      <p class="artifact-label">Pitfalls / Bugs / Mistakes</p>
      ${renderBulletList(globalTask.pitfalls, "暂无明确记录。")}
      <p class="artifact-label">Cross-Task Notes</p>
      ${renderBulletList(globalTask.cross_task_notes, "暂无明确记录。")}
    </article>

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
  const activeTasksFile = fileMap.get("active-tasks.json");
  const activeTaskFile = fileMap.get("active-task.json");

  if (!activeTasksFile && !activeTaskFile) {
    throw new Error("所选目录缺少 active-tasks.json 或 active-task.json。");
  }

  const activeTasks = activeTasksFile
    ? await readJsonFile(activeTasksFile, "active-tasks.json")
    : null;
  const active = activeTaskFile ? await readJsonFile(activeTaskFile, "active-task.json") : null;
  const globalSummary = fileMap.get("global-summary.json")
    ? await readJsonFile(fileMap.get("global-summary.json"), "global-summary.json")
    : defaultGlobalSummary();
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
    activeTasks,
    active,
    globalSummary,
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
    description: "示例：两个并行 active task，各自工作在独立 worktree。",
    activeTasks: {
      focus_task_id: "TASK-008",
      tasks: [
        {
          task_id: "TASK-008",
          title: "实现 DevFlow dashboard",
          task_dir: "tasks/TASK-008",
          status: "developing",
          is_blocked: false,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-008",
          updated_at: "2026-04-14T10:20:00+08:00",
        },
        {
          task_id: "TASK-007",
          title: "设计统一 task 卡片",
          task_dir: "tasks/TASK-007",
          status: "planning",
          is_blocked: false,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-007",
          updated_at: "2026-04-14T08:30:00+08:00",
        },
      ],
    },
    globalSummary: {
      updated_at: "2026-04-14T10:24:00+08:00",
      focus_task_id: "TASK-008",
      active_task_count: 2,
      done_task_count: 1,
      tasks: [
        {
          task_id: "TASK-008",
          title: "实现 DevFlow dashboard",
          status: "developing",
          next_action: "review",
          updated_at: "2026-04-14T10:24:00+08:00",
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-008",
          worktree_branch: "codex/devflow/TASK-008",
          overview: "多 workspace 管理台已具备导入、焦点 task 和任务详情展示能力。",
          key_structures: ["`active-tasks.json` 是多 task 索引真相。", "`active-task.json` 仅作为焦点 task 兼容投影。"],
          key_config: ["前端需要同时读取 `global-summary.json` 和 `tasks/*/meta.json`。"],
          pitfalls: ["不要再把 active task 数量等同于 1。"],
          cross_task_notes: ["新的 task 视图要优先展示 focus task，再展示其他并行 task。"],
        },
      ],
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
          last_completed_step: "confirm multi-task data model",
          next_action: "review",
          is_blocked: false,
          block_reason: null,
          approved_at: "2026-04-14T08:40:00+08:00",
          last_review_verdict: "changes_requested",
          completed_at: null,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-008",
          worktree_branch: "codex/devflow/TASK-008",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-14T10:24:00+08:00",
        },
        docs: {
          "request.md":
            "# Request\n\n给 devflow 做一个管理界面，支持同时打开多个 DevFlowWorkspace 并查看 task 状态。",
          "plan.md":
            "# Plan\n\n先做纯前端管理台，再补导入目录、task 详情和多 workspace 切换。",
          "dev.md":
            "# Dev\n\n已完成 dashboard 骨架、多栏布局和 workspace 解析逻辑。",
          "change-summary.md":
            "# Change Summary\n\n当前只展示 TASK-008 worktree 的差异，不再读取主仓库 working tree。",
          "review.md":
            "# Review\n\n上一轮评审要求补充多 workspace 体验与状态总览。",
          "summary.md":
            "# Summary\n\n这个 task 的重点是浏览器侧的 workspace 解析和焦点 task 展示。",
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
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-007",
          worktree_branch: "codex/devflow/TASK-007",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-14T08:34:00+08:00",
        },
        docs: {
          "request.md":
            "# Request\n\n整理任务卡片展示字段，统一状态、时间和当前步骤的排布。",
          "plan.md":
            "# Plan\n\n对比现有 meta.json 字段，给卡片设计固定信息层级。",
          "summary.md": "# Summary\n\n规划中，尚未进入开发。",
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
          worktree_path: "/Users/demo/.codex/worktrees/devflow/alpha-repo/TASK-006",
          worktree_branch: "codex/devflow/TASK-006",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-13T22:32:00+08:00",
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
    description: "示例：reviewing、blocked 和 plan_approved 并行存在。",
    activeTasks: {
      focus_task_id: "TASK-014",
      tasks: [
        {
          task_id: "TASK-014",
          title: "评审插件市场同步逻辑",
          task_dir: "tasks/TASK-014",
          status: "reviewing",
          is_blocked: false,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-014",
          updated_at: "2026-04-14T09:40:00+08:00",
        },
        {
          task_id: "TASK-013",
          title: "修复 workspace 解析异常",
          task_dir: "tasks/TASK-013",
          status: "developing",
          is_blocked: true,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-013",
          updated_at: "2026-04-14T08:55:00+08:00",
        },
        {
          task_id: "TASK-012",
          title: "整理 workspace 总览指标",
          task_dir: "tasks/TASK-012",
          status: "plan_approved",
          is_blocked: false,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-012",
          updated_at: "2026-04-14T05:15:00+08:00",
        },
      ],
    },
    globalSummary: {
      updated_at: "2026-04-14T09:42:00+08:00",
      focus_task_id: "TASK-014",
      active_task_count: 3,
      done_task_count: 0,
      tasks: [
        {
          task_id: "TASK-014",
          title: "评审插件市场同步逻辑",
          status: "reviewing",
          next_action: "await_review_result",
          updated_at: "2026-04-14T09:42:00+08:00",
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-014",
          worktree_branch: "codex/devflow/TASK-014",
          overview: "评审阶段只读，不应改写任何代码或状态文件。",
          key_structures: ["`review.md` 记录 verdict，`meta.json` 只通过 helper 脚本转移。"],
          key_config: ["review 阶段仍需读取同 task worktree 的 diff。"],
          pitfalls: ["review pass 不是 done。"],
          cross_task_notes: ["其他 task 可以继续 dev，不应被全局单锁阻塞。"],
        },
      ],
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
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-014",
          worktree_branch: "codex/devflow/TASK-014",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-14T09:42:00+08:00",
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
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-013",
          worktree_branch: "codex/devflow/TASK-013",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-14T08:56:00+08:00",
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
          approved_at: "2026-04-14T04:45:00+08:00",
          last_review_verdict: null,
          completed_at: null,
          worktree_path: "/Users/demo/.codex/worktrees/devflow/release-train/TASK-012",
          worktree_branch: "codex/devflow/TASK-012",
          worktree_base_ref: "main",
          global_summary_updated_at: "2026-04-14T05:16:00+08:00",
        },
        docs: {
          "request.md": "# Request\n\n做 workspace 总览指标，区分 focus task、active task 和 done task。",
          "plan.md": "# Plan\n\n统计 workspace 数量、active task 数量、进行中任务和 blocked task。",
          "summary.md": "# Summary\n\n计划已批准，等待开发。",
        },
      },
    ],
  });

  return [exampleA, exampleB];
}

workspaceListElement.addEventListener("click", (event) => {
  const card = event.target.closest("[data-workspace-id]");
  if (!card) {
    return;
  }

  state.selectedWorkspaceId = card.dataset.workspaceId;
  const workspace = selectedWorkspace();
  state.selectedTaskId = workspace?.focusTaskId || workspace?.tasks[0]?.taskId || null;
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
  clearAllWorkspaces();
  for (const workspace of createExampleWorkspaces()) {
    addWorkspace(workspace);
  }
});

clearWorkspacesButton.addEventListener("click", () => {
  clearAllWorkspaces();
});

render();
