我要做一个用于开发的 plugin，负责复杂需求，大型任务开发。
下面是我构思的架构设计，请仔细阅读，并给出和执行的具体计划。如果有需要修改的设计，请与我讨论

## 关键特性：
- 开发 Task 走 workflow： plan -> dev -> review
- 所有状态、决策、进度、审查结果输出 md 文档沉淀：plan.md, dev.md 开发文档, review.md 代码 review
- Skill 为主，不同阶段拆分不同的 Skill。比如 plan-skill，dev-skill，review-skill。
- 多 agent。为优化上下文，独立任务使用 subagent 进行，比如 plan、review 使用 subagent。主 agent 负责流程调度
- 流程可以中断，并恢复。恢复靠文档进度


## SKill 设计
一个Main Skill 和若干Sub Skill 组成。Main skill 负责对用户的接口，Sub skill 负责具体模块，用户不直接与 sub skill 交互。
1. devflow(main skill)
唯一对外入口
职责：
	- 创建任务
	- 读取当前任务状态
	- 调用 gate 判断当前允许动作
	- 路由到 plan/dev/review
	- 给用户返回当前阶段结果

它相当于：
	- front door
	- router
	- session manager
	
2. plan-skill(sub skill)
开启 plan mode，与用户交互设计 plan
负责：
	- 初版计划
	- 多轮更新计划
	- 写 plan.md
	- 写 plan-history.md

3. dev-skill(sub skill)
负责：
	- 按计划执行开发
	- 写 dev-log.md
	- 写 change-summary.md
	
4. review-skill(sub skill)
负责：
	- 审查当前变更
	- 写 review.md
	- 给出 pass / changes_requested / blocked

```test
User
  ↓
devflow（入口 skill）
  ↓
主 agent（在 devflow 内部）
  ├── 调用 plan-skill（skill）
  └── 调用 review-skill（skill）
```



## Agent设计
1. main agent
负责总体流程把控，开发
-	状态推进
-	用户交互
-	最终决策
-	阶段结论
- 开发

职责边界：
负责：
	- workflow 状态推进
	- meta.json 更新
	- 用户交互
	- dev 执行（写代码）
	- 调用 plan / review agent
	- 最终决策（approve / done / rollback）

不能做：
	- 偷懒不走 plan
	- 跳过 review
	- 自己给自己“pass”

2. subagent-plan
负责制定开发计划，输出 plan.md

职责边界：
输入
	- 用户需求
	- 当前 plan（可选）
	- 已知约束

输出
	- 完整 plan.md 内容
	- 或 plan diff
	
不负责
	- 不决定是否进入 dev
	- 不更新 meta.json
	- 不直接执行代码
	- 不和用户对话（由主 agent转述）

3. subagetn-review
负责代码 review，输出 review.md

职责边界：
负责：
- 是否满足需求，审查代码是否按照 plan.md 和 dev.md 进行开发
- 逻辑是否正确
- 边界情况是否遗漏
- 可维护性：逻辑是否合理，命名是否合理等等
- 安全性：是否有安全漏洞

不负责
- 不直接修改代码
- 不更新 meta
- 不决定最终状态（只是建议）

## 重要文件
每个 task 中至少包括下面的文件，可根据具体设计添加其他
1. meta.json
2. plan.md
3. dev.md
4. review.md

## 状态机
```
draft
→ planning
→ plan_approved
→ developing
→ reviewing
→ done

（失败回流）
reviewing → developing
```

## mata.json
记录一个 task 的状态
```json
{
  "task_id": "TASK-001",
  "title": "auth refactor",
  "status": "developing",
  "created_at": "...",
  "updated_at": "...",

  "plan_version": 2,
  "review_round": 1,

  "current_step": "implement session adapter",
  "last_completed_step": "refactor middleware",
  "next_action": "continue_dev",

  "is_blocked": false,
  "block_reason": null
}
```


## 目录结构
在当前项目目录，创建 DevFlowWorkspace。
每个 task 里的文件根据情况调整
```
DevFlowWorkspace/
  active-task.json

  tasks/
    TASK-xxx/
      meta.json
      request.md
      plan.md
      plan-history.md
      dev.md
      change-summary.md
      review.md
      summary.md
```


## 关键行为
 1. start
 ```
 1. 创建 task
 2. 写 request.md
 3. status=planning
 4. 调用 plan skill
 5. 写 plan.md
 ```
 
 2. update
 ```text
 1. 读取 plan.md
 2. 调用 plan skill（带修改意见）
 3. 写 plan.md
 4. 写 plan-history.md
 5. plan_version++
 ```
 
 3. dev
 ```text
 1. 校验 status=developing
 2. 从 plan 拿下一个 task
 3. 主 agent 执行代码
 4. 写 dev.md
 5. 更新 meta.json
 ```
 
 4. review
 ```text
 1. 生成 change-summary.md
 2. 调用 review skill
 3. 写 review.md
 4. 根据 verdict：
    - pass → done
    - fail → developing
 ```
 
 5. resume
 ```text
 1. 读取 active-task.json
 2. 读取 meta.json
 3. 返回状态摘要
 ```


## 强制约束 IMPORTANT
1. 没有 approve plan 不允许 dev
2. plan 不能修改代码，只输出计划
3. review 不能修改代码
4. review 不通过必须回到 dev
5. 所有阶段必须更新 meta.json
