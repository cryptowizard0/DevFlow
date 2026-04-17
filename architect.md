我想在 DevFlow 添加“架构师”的角色，负责大型项目规划，架构设计，写代码规范，工程约束。

- 架构师在 plan->dev->review 更上层。项目开始，先用架构师产出架构规划，清晰的架构文档，拆分出可实施的模块和实现顺序。后面每个 task 再根据规划实现各个模块和功能
- 产出的文档用来约束后面的 agent 开发
- 要考虑开发、review 的 agent 如何使用架构师产出的文档，要有约束
- 架构是可以调整的，但只有架构师可以调整。比如添加新功能，修改特性，架构师总体规划，并做开发计划、模块变更
- 架构师在设计架构前，要与我充分讨论，如果发现不清晰的地方，不要忽略，一定要提出，与我讨论清楚！

## 重要理念
整套系统是一个“文档先行”的约束开发体系，没有被批准的架构文档，就没有 task；没有被引用的约束文档，就不允许开发。

## 架构师的角色
把“架构师”设计成一个 project-scoped 的上层角色，而不是把现有 task 状态机硬改成 architect -> plan -> dev -> review

Architect：项目级角色。负责架构基线、模块拆分、实施顺序、工程约束、代码规范、架构例外审批。
Planner：task 级角色。只能在已批准的架构基线下，为某个 task 生成实施计划。
Developer：实现 task slice。不能擅自突破架构约束。
Reviewer：检查代码正确性，也检查是否违反架构契约；发现偏离时退回，不代替 Architect 改架构。

最重要的几类文档：

architecture.md：系统目标、边界、关键决策、非目标。
module-map.md：模块职责、边界、依赖方向、模块 ID。
standards.md：代码规范、测试要求、错误处理、日志、接口约定。
roadmap.md：模块实施顺序、推荐 task 拆分。
constraints.json：机器可读的约束子集，供后续 gate/check 使用。
adr/：架构决策与例外记录，避免“文档被 silently 改掉”。
task 如何继承架构
每个 task 的 meta.json 增加这些字段最关键：
```text
project_id
architecture_version
module_scope
constraint_refs
exception_ids
architecture_compliance_status
```
这样 task 就不是孤立的，而是“在某个架构版本下，对某几个模块做实现”。

Planner / Dev / Reviewer 怎么使用这些文档
最核心的是：不要把架构文档当“参考阅读材料”，而要当“约束输入”。

Planner 阶段：

读取 architecture_version、module_scope、相关 ADR。
plan.md 必须新增几个固定 section：
Architecture Context
Modules In Scope
Constraints Checklist
Required Exceptions
Implementation Order
approve-plan 前检查这些 section 是否齐全。
Dev 阶段：

只注入与当前 module_scope 相关的架构片段，不要把整套文档塞进 prompt。
开发 agent 必须明确声明“本次实现遵守哪些约束”。
如果实现需要突破约束，只能提出 architecture change request，不能自己改规则。
Review 阶段：

Reviewer 不只看 correctness，还必须给出第二个维度的 verdict：
implementation_verdict: pass | changes_requested | blocked
architecture_verdict: compliant | deviation | needs_architect_decision
只有 pass + compliant，或者 pass + approved exception，才允许 done。
