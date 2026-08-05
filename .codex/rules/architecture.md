# 架构规则

## 事实来源

发生冲突时按以下顺序判断当前行为：

1. 当前代码、测试和公开请求/响应契约。
2. `CONTEXT.md` 中的领域术语和所有权。
3. `docs/adr/` 中状态为 accepted 的决策。
4. `docs/README.md` 标记为 current 的文档。

计划只表达意图，不能证明功能已经实现。过期、历史或已删除功能的计划不得作为实现依据。

## 统一语言

架构讨论和规则使用以下术语：

- **Module**：具有一个 Interface 和一个 Implementation 的代码单元。
- **Interface**：调用者必须知道的类型、不变量、顺序、错误模式、配置和性能特征。
- **Implementation**：Module 内部代码。
- **Depth**：一个小 Interface 提供大量行为的程度。
- **Seam**：无需在原地编辑即可替换行为的位置。
- **Adapter**：在 Seam 上满足 Interface 的具体实现。
- **Leverage**：调用者从 Depth 获得的复用收益。
- **Locality**：修改、知识、错误和验证集中在一个位置。

使用 `CONTEXT.md` 中的领域名称，例如 Upstream Account、User Key、Image Task、Call Record、Proxy Reference 和 Account Storage Backend。不要用含混的“账号”“用户”“运行时代理”替代已经定义的概念。

## 唯一所有者

- 每一项业务语义、业务操作、状态转换、请求生命周期、并发配额、缓存、持久化、加载状态、选择状态、布局和滚动行为都必须有且只有一个权威所有者。
- 权威 Module 通过稳定 Interface 输出投影、命令结果或事件；调用者只能消费这些结果，不得维护第二份镜像状态、优先级、派生规则或清理时机。
- 跨 Module 的编排必须指定一个生命周期所有者。其他 Module 只作为 Adapter 参与，不得各自启动、结束、重试或回滚同一生命周期。
- 前端可以拥有草稿、筛选、焦点和临时展示状态，但不得反算后端已经投影的业务状态、能力和下一操作；后端不得拥有浏览器布局、焦点或滚动状态。
- 新增状态或规则前先指出现有所有者；若无法指出，先建立所有权与 Interface，再实现功能。测试应穿过该 Interface 验证唯一事实来源，而不是分别固化多份 Implementation。

## 前后端职责

数据流固定为：

```text
domain and persistence Implementation
  -> backend projection and action result
  -> web-vue transport Adapter
  -> page interaction state and rendering
```

- 每个业务概念只有一个权威后端投影。投影必须用显式优先级解决持久状态、凭据状态和运行时结果之间的冲突，并返回最终状态、标签、tone、capabilities 与下一步允许的操作。
- 前端 Adapter 校验和传输契约；页面拥有草稿、筛选、选择、弹窗、图表、加载生命周期和响应式布局。
- 前端不得通过错误文本、HTTP 状态、`enabled` 等原始字段重新计算后端已经投影的状态、能力或下一操作。
- 纯视觉格式可以留在前端，但同一业务含义被多个页面消费时必须由后端统一投影。

## 持久化所有权

- Account Storage Backend 只存储 Upstream Accounts 和 User Keys。
- 配置、Call Records、指标、Image Tasks、Editable File Tasks、Image Assets 和 Prompt Library 各有独立持久化责任。
- 不得把 `STORAGE_BACKEND` 解释为全局存储开关。
- 不得仅为“统一”迁移日志、代理、设置、图片或任务存储。改变所有权必须先分析迁移、并发、恢复、回滚和运维成本，并由用户明确授权及 ADR 记录。
- Image Asset 变更必须经过 `ImageStorageService`，遵循 ADR 0003；调用者不得绕过其 Seam 直接改索引或文件。

## Module 设计

- 使用删除测试判断抽象价值：删除后复杂度若在多个调用者中重现，Module 有 Depth；若复杂度直接消失，它可能只是浅包装。
- 一种 Adapter 只是预想的 Seam；存在两个真实 Adapter 或明确替换需求时再固定公共 Interface。
- 测试应穿过与调用者相同的 Interface，不以拆出大量纯函数代替真实编排验证。
- 当跨层语义变化时，先修改后端投影与契约测试，再修改前端 Adapter 和渲染。
- 与 accepted ADR 冲突的修改必须显式提出是否重开决策，不能静默绕过。
