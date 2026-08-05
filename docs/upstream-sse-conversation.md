# 上游 Conversation SSE 与图片结果解析

状态：当前

这是内部协议参考，不是公开 API 契约。上游事件格式会变化；公开调用方只应依赖本项目的 OpenAI 兼容 API 和图片任务接口。

## 输入和解析层

上游 Conversation 链路会返回 SSE `data:` 事件。事件可能是版本标记、`[DONE]`、完整 JSON 消息、JSON patch、文本片段或无法解析的原始内容。解析层保留会话 ID、消息事实、文本、工具信号和原始诊断，而不是假设每个事件都是同一种 JSON。

常见线索包括：

| 线索 | 含义 |
| --- | --- |
| `conversation_id` | 后续读取会话或任务的关联键 |
| `p` / `o` / `v` | 上游 patch 的路径、操作和值 |
| `message.author.role` | 消息角色，如 assistant、tool、user |
| `message.status` / `end_turn` | 该消息是否可能是终态 |
| `tool_invoked` | 上游报告本轮使用了工具的线索 |
| `turn_use_case`、`async_task_type`、`message_type` | 工具或使用场景的附加线索 |

这些字段都只是解析事实。`tool_invoked=true` 或 `async_task_type=image_gen` 说明可能需要继续解析或补查，但本身不等于图片已经成功生成。

## 图片成功判定

图片成功必须得到可用的输出资产。Conversation SSE 只会从受信任的工具消息和 patch 上下文收集有效的 `file_` / `sediment://` 输出指针，随后由后端解析和下载资源；仅仅看到输入附件或工具信号不能当作输出图片。`data:image/...`、base64 或直接结果 URL 属于独立的 Codex 图片响应路径，不能当作一般 Conversation SSE 的结果规则。

SSE 未携带完整结果时，后端会根据已有的 `conversation_id`、任务事实和流状态继续读取会话或图片任务，再决定是否有输出资产、文本结果或失败。这个补查过程属于后端协议层；Studio 和其他页面不自行轮询上游 Conversation。

## 文本、JSON 和失败

没有有效图片资产时，终态 assistant 的普通文本 / 代码内容会分类为 `upstream_text_reply`，按 HTTP 400 的图片文本结果返回。它不是账号失败，也不会触发账号切换。

如果终态内容或任务事件包含结构化错误、明确失败码、工具 `system_error`、限流、鉴权失效或审核信号，后端通过 `ImageFailure` 归类为相应失败。参数 JSON 或其他结构化 JSON 只有在它表达图片工具异常时才会成为 `image_tool_error`；不能因为内容“看起来像 JSON”就把正常结果判错。

当既没有图片结果、也没有可展示文本或明确失败证据时，后端返回受控的空结果 / 上游错误，而不是让前端从 SSE 片段猜测。

## 诊断与边界

图片执行使用 `ImageFailure` 产生对外错误、上游错误、上游文本和结构化失败字段。API 和账号切换使用当前分类；日志、监控和历史尝试使用这些持久化字段生成兼容投影。详情见 [`image-failure-handling.md`](image-failure-handling.md)。

修改解析规则时必须同时覆盖：SSE 事件、完整会话补查、图片任务补查、文本终态、结构化错误终态、限流、鉴权和多图部分成功。不要在前端增加第二套判断逻辑。
