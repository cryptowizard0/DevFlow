# DevFlow Workspace Console

一个可直接在浏览器中打开运行的零依赖 DevFlow 管理界面，用来查看多个 `DevFlowWorkspace` 的任务列表、当前 task、任务状态和关键文档摘要。

## 运行方式

这个界面现在作为插件静态资产一起打包，真实入口在：

- [plugins/devflow/assets/console/index.html](/Users/webbergao/work/src/DevFlow/plugins/devflow/assets/console/index.html)

仓库根下的 [index.html](/Users/webbergao/work/src/DevFlow/index.html) 只是一个跳转页，方便本地开发时直接打开。

如果想从插件目录稳定定位并打开界面，可以运行：

- `python3 plugins/devflow/scripts/open_console.py`
- `python3 plugins/devflow/scripts/open_console.py --print-path`

推荐使用 Chrome / Edge / Safari，这些浏览器对目录导入支持更稳定。

## 支持的能力

- 重复导入多个本地 `DevFlowWorkspace`
- 识别当前 workspace 的 `active-task.json`
- 列出 `tasks/*/meta.json` 下的所有任务
- 展示当前 task、task 状态、next action、review verdict、更新时间
- 查看 `request.md`、`plan.md`、`dev.md`、`change-summary.md`、`review.md`、`summary.md` 的摘要
- 提供示例数据，方便在没有本地目录时先预览界面

## 导入说明

点击页面上的“导入 Workspace”后，可以选择：

- 仓库根目录，只要其中包含 `DevFlowWorkspace/`
- 直接选择 `DevFlowWorkspace/` 目录

每次导入一个目录；如需同时查看多个 workspace，重复导入即可。

页面会读取以下结构：

```text
DevFlowWorkspace/
├── active-task.json
└── tasks/
    └── TASK-xxx/
        ├── meta.json
        ├── request.md
        ├── plan.md
        ├── dev.md
        ├── change-summary.md
        ├── review.md
        └── summary.md
```

其中只有 `active-task.json` 和 `tasks/*/meta.json` 是强依赖；其余文档缺失时仍可正常显示，只是不展示对应摘要。

## 文件说明

- [plugins/devflow/assets/console/index.html](/Users/webbergao/work/src/DevFlow/plugins/devflow/assets/console/index.html)：插件内的页面入口
- [plugins/devflow/assets/console/styles.css](/Users/webbergao/work/src/DevFlow/plugins/devflow/assets/console/styles.css)：视觉风格、响应式布局和状态样式
- [plugins/devflow/assets/console/app.js](/Users/webbergao/work/src/DevFlow/plugins/devflow/assets/console/app.js)：workspace 导入、任务解析和 UI 渲染逻辑
- [plugins/devflow/scripts/open_console.py](/Users/webbergao/work/src/DevFlow/plugins/devflow/scripts/open_console.py)：解析插件内 console 入口并可直接调用默认浏览器打开

## 最小验证

- `node --check plugins/devflow/assets/console/app.js`
- `python3 plugins/devflow/scripts/open_console.py --print-path`

这个检查只覆盖 JavaScript 语法。目录导入和页面交互需要在浏览器中手动验证。
