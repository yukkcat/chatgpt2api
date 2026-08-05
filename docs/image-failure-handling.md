# 图片失败处理

状态：当前

## 单一分类来源

`services/image_failure.py` 中的 `ImageFailure` 是图片执行期间的统一分类对象。它携带失败码、作用域、能力、是否可重试、HTTP 状态、错误类型、原始诊断和对外文案。执行、账号处理和 API 响应使用当前分类结果；调用日志、实时监控和历史尝试则消费其持久化的结构化失败字段，并为旧记录做兼容投影。任何一层都不应再按错误文本重新分类。

## 文本结果与失败

HTTP 400 的图片结果被分类为文本结果：`content_policy_violation`、`invalid_image_input`、`upstream_text_reply` 和 `unsupported_model`。这类结果会保留可展示的上游文本，不将账号切换或账号记失败。

其他 `ImageFailure` 的 `outcome` 是失败，允许执行账号切换与账号验证流程。是否实际切换还取决于账号池、尝试上限和当前设置；分类对象只给出一致的切换资格，不保证一定能找到下一个账号。

常见类别包括：

| 类别 | 典型含义 | 对外状态 |
| --- | --- | --- |
| `auth_invalid` | 上游鉴权无效 | 401 |
| `upstream_rate_limited` / `image_quota_exhausted` | 限流或图片额度耗尽 | 429 |
| `image_poll_timeout` | 等待图片结果超时 | 502 |
| `image_stream_timeout` / `image_stream_interrupted` | SSE 超时或中断 | 502 |
| `image_tool_error` | 上游图片工具终态异常 | 502 |
| `image_download_failed` | 已生成但交付下载失败 | 502 |
| `no_available_account` | 当前账号池无法选择账号 | 503 |

## 诊断字段

日志和尝试详情区分三种信息：

- **对外错误**：返回给 API 调用方的安全文案。
- **上游错误**：上游结构化错误或异常摘要。
- **上游文本**：上游 assistant 返回的原始可读文本。

结构化 JSON 不会被误当作用户可读文本直接展示。终态 assistant 普通文本会保留为文本结果；当终态 JSON / 结构化字段明确表示图片工具失败时，后端归为 `image_tool_error` 或更具体的失败码。

## 图片任务与对外投影

`ImageTaskService` 持久化的任务状态是 `queued`、`running`、`success` 或 `error`。`/api/image-tasks` 的视图投影会根据原始状态、请求数量、成功数量和失败分类对外呈现 `success`、`partial_success`、`failed` 或 `text_review`。`partial_success` 用于多张请求中已有结果但未全部完成；`text_review` 是文本结果，不是前端把 400 临时改名后的失败。

更改图片失败策略时，先调整 `ImageFailure` 的策略和契约测试，再检查 API、账号切换、持久化诊断、日志、监控和 Studio 投影是否一致。
