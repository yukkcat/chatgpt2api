// Chinese -> English console text. Placeholders: $n inserts capture n, ‹n|one|other› picks a plural form from capture n.
export const enExact: Record<string, string> = {
 "1 张": "1 image",
 "2 张": "2 images",
 "24小时": "24 hours",
 "3 张": "3 images",
 "30天": "30 days",
 "4 张": "4 images",
 "7天": "7 days",
 ": '从一个或多个 CPA JSON 文件提取账号凭据，并请求远程接口验证、同步账号信息与额度。'\"": ": 'Extracts account credentials from one or more CPA JSON files, then verifies them against the remote API and syncs account info and quota.'\"",
 "<button type=\"button\" class=\"studio-code-copy\" title=\"复制代码\">复制</button>": "<button type=\"button\" class=\"studio-code-copy\" title=\"Copy code\">Copy</button>",
 "<当前密钥>": "<current key>",
 "? '读取 Sub2API 导出的 JSON 文件，提取账号凭据并同步账号信息与额度。'": "? 'Reads a JSON file exported from Sub2API, extracts the account credentials, and syncs account info and quota.'",
 "AI 审核": "AI review",
 "API 接口": "API endpoints",
 "Access token 不能为空": "Access token cannot be empty",
 "Anthropic Messages 兼容入口，支持 Authorization Bearer 或 x-api-key 鉴权。": "Anthropic Messages-compatible endpoint; supports Authorization Bearer or x-api-key authentication.",
 "Application Database 始终包含": "Application Database is always included",
 "Bucket 名称": "Bucket name",
 "CPA 地址": "CPA URL",
 "CPA 服务器": "CPA server",
 "CPA 管理密钥": "CPA management key",
 "CPA 连接已保存": "CPA connection saved",
 "CPA 连接已删除": "CPA connection deleted",
 "CPA 连接测试失败": "CPA connection test failed",
 "CPA 连接管理": "CPA connection management",
 "CPU 容量": "CPU capacity",
 "ChatGPT2API 更新": "ChatGPT2API update",
 "GenBox 图片推送": "GenBox image push",
 "GenBox 地址": "GenBox URL",
 "Lane 详情": "Lane details",
 "OAuth 凭据已保存，但同步失败": "OAuth credentials saved, but sync failed",
 "OAuth 授权链接已生成": "OAuth authorization link generated",
 "OAuth 登录导入": "OAuth login import",
 "OAuth 登录导入失败": "OAuth login import failed",
 "OAuth 登录已有账号": "Sign in to an existing account via OAuth",
 "OpenAI 兼容聊天补全接口，图片兼容场景也会解析 n 等参数。": "OpenAI-compatible chat completions endpoint. Image-compatible scenarios also parse parameters such as n.",
 "PPT / PSD 文件": "PPT / PSD files",
 "PPT 与 PSD 任务记录": "PPT and PSD task history",
 "PPT 生成任务": "PPT generation task",
 "PSD 文件任务至少需要上传一张原图": "A PSD file task requires at least one original image",
 "PSD 生成任务": "PSD generation task",
 "Push 失败": "Push failed",
 "Push 成功": "Push succeeded",
 "QQ 交流群：1005859624": "QQ group: 1005859624",
 "R2 / 备份存储": "R2 / Backup storage",
 "R2 备份": "R2 backup",
 "R2 备份管理": "R2 backup management",
 "RT（可选）": "RT (optional)",
 "SDK 接口": "SDK endpoint",
 "Session JSON 中没有找到 accessToken": "No accessToken found in the Session JSON",
 "Session JSON 格式不正确": "Invalid Session JSON format",
 "Studio 只读取本地快照；更新时从": "Studio only reads the local snapshot; when updating, it downloads from",
 "Studio 成功后自动推送": "Auto-push after Studio succeeds",
 "Sub2API 分组": "Sub2API group",
 "Sub2API 地址": "Sub2API URL",
 "Sub2API 导入失败": "Sub2API import failed",
 "Sub2API 服务器": "Sub2API server",
 "Sub2API 连接已保存": "Sub2API connection saved",
 "Sub2API 连接已删除": "Sub2API connection deleted",
 "Sub2API 连接测试失败": "Sub2API connection test failed",
 "Sub2API 连接管理": "Sub2API connection management",
 "WebDAV 不可用": "WebDAV unavailable",
 "WebDAV 可用": "WebDAV available",
 "WebDAV 测试失败": "WebDAV test failed",
 "WebDAV 测试通过": "WebDAV test passed",
 "ZIP 已生成，正在启动下载...": "ZIP ready. Starting download...",
 "http://127.0.0.1:7890 或 socks5://127.0.0.1:7890": "http://127.0.0.1:7890 or socks5://127.0.0.1:7890",
 "一个代理组就是一组多出口节点；图片请求会从未满的节点里随机选择一个，请求结束前固定该出口，出口满了会等待，不会自动绕到直连。": "A proxy group is a set of egress nodes. Image requests pick a random node that is not full and stay on that egress until the request finishes. If every node is full, requests wait; they never fall back to a direct connection automatically.",
 "一只慵懒的猫咪蜷在柔软毛毯上睡觉，午后暖光，温馨室内，细节丰富，治愈系插画。": "A lazy kitten curled up asleep on a soft blanket, warm afternoon light, cozy interior, rich detail, healing-style illustration.",
 "一行一个 access token": "One access token per line",
 "一行一个，命中即拒绝": "One per line; a match is rejected",
 "上一页": "Previous",
 "上传图片": "Upload image",
 "上游文本": "Upstream text",
 "上游没有返回内容。": "Upstream returned no content.",
 "上游没有返回可用图片。": "The upstream service did not return a usable image.",
 "上游错误": "Upstream error",
 "下一页": "Next",
 "下载": "Download",
 "下载 ZIP": "Download ZIP",
 "下载失败": "Download failed",
 "下载并覆盖本地快照。": "and overwrites the local snapshot.",
 "下载文件": "Download file",
 "不可用": "Unavailable",
 "不绑定账号组": "No account group",
 "不选择任何级别时使用默认 info / warning / error。": "When no level is selected, the default info / warning / error is used.",
 "不限": "Unlimited",
 "个账号": "accounts",
 "中": "Medium",
 "中文": "Chinese",
 "主 CPA": "Primary CPA",
 "二次确认等待（秒）": "Double-check wait (seconds)",
 "云端": "Cloud",
 "交流与服务": "Community and services",
 "仅 WebDAV": "WebDAV only",
 "仅图片请求在早期 TLS / 连接超时且尚未收到上游事件时重试一次；生成中断和轮询超时不会切换。": "Image requests only retry once on an early TLS / connection timeout, before any upstream event is received; generation interruptions and polling timeouts do not switch egress.",
 "仅本地": "Local only",
 "仅统计成功及部分成功请求。": "Only successful and partially successful requests are counted.",
 "从 CPA 导入账号": "Import accounts from CPA",
 "从 Sub2API 导入": "Import from Sub2API",
 "从 Sub2API 导入账号": "Import accounts from Sub2API",
 "从 Sub2API 服务器导入": "Import from Sub2API server",
 "从一个或多个 CPA JSON 文件提取账号凭据，并请求远程接口验证、同步账号信息与额度。": "Extracts account credentials from one or more CPA JSON files, then verifies them against the remote API and syncs account info and quota.",
 "从远程 CPA 导入": "Import from remote CPA",
 "从远程 CPA 服务器导入": "Import from remote CPA server",
 "代理 URL": "Proxy URL",
 "代理模式": "Proxy mode",
 "代理管理": "Proxies",
 "代理组": "Proxy group",
 "代理组 / 多出口": "Proxy Groups / Multiple Egress",
 "代理组 ID": "Proxy group ID",
 "代理组名称": "Proxy group name",
 "代理组已创建": "Proxy group created",
 "代理组已删除": "Proxy group deleted",
 "代理组已更新": "Proxy group updated",
 "代理组引用已复制": "Proxy group reference copied",
 "代理组检测失败": "Proxy group check failed",
 "代理组（多节点）": "Proxy group (multiple nodes)",
 "代理组：未选择": "Proxy group: not selected",
 "代理节点": "Proxy nodes",
 "任务": "Task",
 "任务记录": "Task log",
 "任务记录和本地文件已删除。": "Task record and local files have been deleted.",
 "任务运行中，暂时无法关闭": "Task is running and cannot be closed yet",
 "任务进度": "Task progress",
 "优先读取后端本地快照，不等待云端词源。": "s local snapshot first and doesn",
 "低": "Low",
 "你会收到两张参考图：第一张是原图，第二张是带蓝色标记的原图。": "You will receive two reference images: the first is the original image, the second is the original image with blue markings.",
 "使用": "Use",
 "使用默认代理": "Use default proxy",
 "使用默认出口": "Use default egress",
 "例如：先判断用户提示词是否合规；遇到违法、色情、暴力、仇恨等请求时拒绝回答。": "Example: First check whether the user prompt is compliant; refuse requests involving illegal, pornographic, violent, or hateful content.",
 "例如：运营画图账号": "Example: Marketing image account",
 "例如：高额度账号默认走香港代理池": "e.g. High-quota accounts use the Hong Kong proxy pool by default",
 "保存": "Save",
 "保存 CLIProxyAPI 地址和管理密钥，供远程 CPA 导入使用。": "Save the CLIProxyAPI address and management key for remote CPA import.",
 "保存 CPA 连接失败": "Failed to save CPA connection",
 "保存 Sub2API 服务器，用于读取 OpenAI OAuth 账号并导入本地号池。": "Save a Sub2API server to read OpenAI OAuth accounts and import them into the local pool.",
 "保存 Sub2API 连接失败": "Failed to save Sub2API connection",
 "保存中...": "Saving...",
 "保存代理组失败": "Failed to save proxy group",
 "保存出口配置": "Save egress settings",
 "保存出口配置失败": "Failed to save egress settings",
 "保存失败": "Save failed",
 "保存成功": "Saved",
 "保存标签": "Save tags",
 "保存标签失败": "Failed to save tags",
 "保存设置": "Save settings",
 "保存账号": "Saving accounts",
 "保存账号组": "Save account group",
 "保留份数": "Backups to keep",
 "保留来源分组": "Keep source group",
 "停止": "Stop",
 "停止中": "Stopping",
 "停止中...": "Stopping...",
 "停止输出": "Stop generating",
 "停用": "Disabled",
 "停用代理组": "Disable proxy group",
 "健康": "Health",
 "先保留": "Keep for now",
 "先创建账号组，再在账号列表勾选账号批量绑定。": "Create an account group first, then select accounts in the list to bind them in bulk.",
 "入站速率": "Inbound rate",
 "全局系统提示词": "Global system prompt",
 "全局附加指令": "Global additional instructions",
 "全屏": "Fullscreen",
 "全选": "Select all",
 "全选当前视图图片": "Select all images in the current view",
 "全选当前页日志": "Select all logs on this page",
 "全选当前页账号": "Select all accounts on the current page",
 "全选本组": "Select group",
 "全选本页": "Select all on this page",
 "全选筛选": "Select all filtered",
 "全选账号": "Select all accounts",
 "全部": "All",
 "全部来源": "All sources",
 "全部标签": "All tags",
 "全部模型": "All models",
 "全部状态": "All statuses",
 "全部类型": "All types",
 "全部账号": "All accounts",
 "全部账号 · Access Token TXT": "All accounts · Access Token TXT",
 "全部账号 · 完整 JSON": "All accounts · Full JSON",
 "全部账号组": "All account groups",
 "全部账号（按远端分组）": "All accounts (by remote group)",
 "全量同步": "Full sync",
 "全量同步图片": "Full image sync",
 "公开下载 PPT/PSD 任务生成的文件或压缩包，无需鉴权。": "Publicly download files or archives generated by PPT/PSD tasks; no authentication required.",
 "公开访问前缀": "Public access prefix",
 "关键耗时": "Key timings",
 "关闭": "Close",
 "关闭任务记录": "Close task log",
 "关闭历史记录": "Close history",
 "关闭存储管理": "Close storage management",
 "关闭预览": "Close preview",
 "兼容 Responses 输入结构，支持文本与工具调用场景。": "Compatible with the Responses input structure; supports text and tool-calling scenarios.",
 "内核 / 架构": "Kernel / architecture",
 "内置": "Built-in",
 "准备就绪": "Ready",
 "凭据状态": "Credential status",
 "出口": "Egress",
 "出口优先级：账号个人代理 > 账号组代理/代理组 > 默认出口；默认出口可配置代理组、代理 URL 或直连。": "Egress priority: account proxy > account group proxy / proxy group > default egress. The default egress can be a proxy group, a proxy URL, or a direct connection.",
 "出口配置已保存": "Egress settings saved",
 "出站速率": "Outbound rate",
 "分辨率": "Resolution",
 "切号": "Switches",
 "切换代理组失败": "Failed to toggle proxy group",
 "切换恢复率": "Switch recovery rate",
 "切换模式": "Switch mode",
 "列表布局": "List layout",
 "列表视图": "List view",
 "创建": "Create",
 "创建中...": "Creating...",
 "创建可编辑文件任务": "Create editable file task",
 "创建时间": "Created",
 "创建用户密钥": "Create user key",
 "创建用户密钥失败": "Failed to create user key",
 "创建给普通用户使用的调用密钥；普通用户登录后只进入对话画图页。": "Create API keys for regular users; after signing in, regular users only reach the chat and image page.",
 "创建账号组": "Create account group",
 "创建账号组失败": "Failed to create account group",
 "删除": "Delete",
 "删除 CPA 连接": "Delete CPA connection",
 "删除 CPA 连接失败": "Failed to delete CPA connection",
 "删除 Sub2API 连接": "Delete Sub2API connection",
 "删除 Sub2API 连接失败": "Failed to delete Sub2API connection",
 "删除中...": "Deleting...",
 "删除代理组": "Delete proxy group",
 "删除代理组失败": "Failed to delete proxy group",
 "删除图片": "Delete image",
 "删除图片失败": "Failed to delete image",
 "删除备份": "Delete backup",
 "删除备份失败": "Failed to delete backup",
 "删除失败": "Delete failed",
 "删除完成，正在刷新列表...": "Deleted. Refreshing list...",
 "删除对话": "Delete chat",
 "删除文件任务": "Delete file task",
 "删除文件任务失败": "Failed to delete file task",
 "删除日志": "Delete log",
 "删除用户密钥": "Delete user key",
 "删除用户密钥失败": "Failed to delete user key",
 "删除账号": "Delete account",
 "删除账号组": "Delete account group",
 "删除账号组失败": "Failed to delete account group",
 "判断用户请求是否允许。只回答 ALLOW 或 REJECT。": "Decide whether the user request is allowed. Answer only ALLOW or REJECT.",
 "到期时间": "Expires at",
 "刷新": "Refresh",
 "刷新 AT": "Refresh AT",
 "刷新 AT 中...": "Refreshing AT...",
 "刷新中": "Refreshing",
 "刷新中...": "Refreshing...",
 "刷新代理组": "Refresh proxy groups",
 "刷新列表": "Refresh list",
 "刷新历史": "Refresh history",
 "刷新图片任务失败": "Failed to refresh image tasks",
 "刷新失败": "Refresh failed",
 "刷新存储统计失败": "Failed to refresh storage stats",
 "刷新密钥": "Refresh keys",
 "刷新当前页面": "Refresh current page",
 "刷新文件任务失败": "Failed to refresh file tasks",
 "刷新来源": "Refresh sources",
 "刷新统计": "Refresh stats",
 "刷新记录": "Refresh records",
 "刷新连接": "Refresh connections",
 "剩余空间": "Free space",
 "剩余额度": "Remaining quota",
 "加密口令": "Encryption passphrase",
 "加载 CPA 文件失败": "Failed to load CPA files",
 "加载 CPA 连接失败": "Failed to load CPA connections",
 "加载 Sub2API 分组失败": "Failed to load Sub2API groups",
 "加载 Sub2API 账号失败": "Failed to load Sub2API accounts",
 "加载 Sub2API 连接失败": "Failed to load Sub2API connections",
 "加载中...": "Loading...",
 "加载代理配置失败": "Failed to load proxy settings",
 "加载全部": "Load all",
 "加载图片管理失败": "Failed to load image management",
 "加载备份历史失败": "Failed to load backup history",
 "加载失败": "Failed to load",
 "加载文件": "Load files",
 "加载模型中...": "Loading models...",
 "加载用户密钥失败": "Failed to load user keys",
 "加载账号": "Load accounts",
 "加载账号组失败": "Failed to load account groups",
 "加载账号详情失败": "Failed to load account details",
 "包含第一次使用的账号。默认 4，最小 2，不限制可填写的最大值。": "Includes the first account used. Defaults to 4, minimum 2, with no upper limit on the value you can enter.",
 "单位分钟，控制待核验账号、限流账号和临期 AT 的后台处理频率。": "In minutes. Controls how often background processing runs for accounts pending verification, rate-limited accounts, and AT tokens that are about to expire.",
 "单位秒，SSE 流结束后继续等待上游图片结果的最长时间。": "In seconds. The longest to keep waiting for the upstream image result after the SSE stream ends.",
 "单位秒，两次图片结果查询之间的等待时间。": "In seconds. The wait time between two image result queries.",
 "单位秒，开始查询图片结果前先等待的时间。": "In seconds. How long to wait before starting to query for the image result.",
 "单位秒，控制日志、图片、账号和设置等控制台请求等待后端响应的最长时间。": "In seconds. The longest the console waits for a backend response on requests such as logs, images, accounts, and settings.",
 "单位秒，限制 ChatGPT 生图 SSE 流的等待时间。": "In seconds. Limits how long to wait on the ChatGPT image-generation SSE stream.",
 "单账号图片并发": "Image concurrency per account",
 "卡片视图": "Card view",
 "即将使用已保存的图片存储配置发起 WebDAV 连接测试，可能访问外部存储服务。是否继续？": "This will use the saved image storage configuration to test the WebDAV connection, which may contact an external storage service. Continue?",
 "即将使用已保存的备份配置发起 R2/备份存储连接测试，可能访问外部存储服务。是否继续？": "This will use the saved backup configuration to test the R2/backup storage connection, which may contact an external storage service. Continue?",
 "即将使用当前默认出口发起外部网络测试请求。请确认当前允许测试该出口连接。": "This will send an external network test request through the current default egress. Confirm that testing this egress connection is allowed.",
 "即将保存当前系统设置，可能影响接口地址、并发、存储和备份策略。是否继续？": "You are about to save the current system settings, which may affect API addresses, concurrency, storage, and backup policies. Continue?",
 "即将保存默认出口和备用出口配置。备用出口只在图片请求早期连接失败时重试一次，是否继续？": "This will save the default and fallback egress settings. The fallback egress only retries once when an image request fails early in the connection. Continue?",
 "即将打开外部画布，并附带当前接口地址和当前调用密钥。是否继续？": "This will open an external canvas and pass along the current API endpoint and API key. Continue?",
 "即将扫描本地图片并同步到已配置的 WebDAV 存储，可能产生外部上传流量。是否继续？": "This will scan local images and sync them to the configured WebDAV storage, which may generate outbound upload traffic. Continue?",
 "即将把当前配置和运行数据写入备份存储，可能产生外部上传流量。是否继续？": "This will write the current configuration and runtime data to backup storage, which may generate outbound upload traffic. Continue?",
 "即将通过当前账号代理配置发起外部网络测试请求。请确认当前允许测试该代理连接。": "This will send an external network test request through the current account proxy settings. Confirm that testing this proxy connection is allowed.",
 "历史记录": "History",
 "压缩图片": "Compress images",
 "压缩图片失败": "Failed to compress images",
 "压缩失败": "Compression failed",
 "压缩完成": "Compression complete",
 "原图": "Original",
 "原图未加载": "The original image has not loaded",
 "原始 detail JSON": "Raw detail JSON",
 "原始报错": "Raw error",
 "参数错误": "Invalid input",
 "参考图": "Reference image",
 "参考来源": "Sources",
 "反选": "Invert",
 "反选区域": "Invert selection",
 "发送": "Send",
 "发送消息": "Send message",
 "取消": "Cancel",
 "取消分组": "Remove from group",
 "取消选择": "Clear selection",
 "只修改蓝色标记覆盖的局部区域，蓝色标记只是区域说明，不要出现在最终图片里。": "Only edit the local area covered by the blue markings. The blue markings only describe the area and must not appear in the final image.",
 "只有远程明确确认图片额度为 0 时才会处理，代理错误、断流或上游 429 不会删除账号。": "Only handled when the remote side explicitly confirms the image quota is 0. Proxy errors, dropped streams, or upstream 429 responses will not delete an account.",
 "只看失败": "Failed only",
 "只读取本地词源配置和同步状态。": "Only reading the local source configuration and sync status.",
 "可下载源文件或完整压缩包。": "Source files or the full ZIP archive can be downloaded.",
 "可以修改备注名称；填写新的专用密钥会让旧密钥失效。": "You can change the note name; entering a new dedicated key invalidates the old key.",
 "可以先用 OAuth 登录已有账号，也可以导入 Access Token、Session JSON 或账号 JSON 文件。": "Start by signing in to an existing account with OAuth, or import an Access Token, Session JSON, or account JSON file.",
 "可替代邮箱密码": "Can replace email and password",
 "可用": "Available",
 "可见内存": "Visible memory",
 "可选": "Optional",
 "同步": "sync",
 "同步中...": "Syncing...",
 "同步图片失败": "Failed to sync images",
 "同步本地图片": "sync local images",
 "同步账号与额度": "Syncing accounts and quota",
 "名称": "Name",
 "名称只是备注；创建后会生成一条只展示一次的原始密钥。": "The name is just a note; creating the key generates a raw key that is shown only once.",
 "后台继续执行": "Continuing in the background",
 "后台维护间隔": "Background maintenance interval",
 "后端未返回更新后的账号": "The backend did not return the updated account",
 "后端没有返回 CPA 导入任务": "The backend did not return a CPA import task",
 "后端没有返回 Sub2API 导入任务": "The backend did not return a Sub2API import task",
 "后端没有返回完整的 OAuth 授权会话": "The backend did not return a complete OAuth authorization session",
 "启动下载": "Start download",
 "启用": "Enabled",
 "启用 AI 审核": "Enable AI review",
 "启用 GenBox Push": "Enable GenBox Push",
 "启用 WebDAV 图片存储": "Enable WebDAV image storage",
 "启用代理组": "Enable proxy group",
 "启用备份加密": "Enable backup encryption",
 "启用定时备份": "Enable scheduled backups",
 "启用无限画布入口": "Enable infinite canvas entry",
 "启用账号组": "Enable account group",
 "图像编辑任务已提交": "Image edit task submitted",
 "图库占用": "Gallery usage",
 "图库总量": "Total images",
 "图库文件": "Gallery files",
 "图片": "Images",
 "图片二次确认机制": "Image double-check mechanism",
 "图片任务已提交": "Image task submitted",
 "图片任务已过期或不存在": "The image task has expired or does not exist",
 "图片任务提交失败": "Image task submission failed",
 "图片任务记录": "Image task records",
 "图片参考": "Image reference",
 "图片存储": "Image storage",
 "图片存储与审核": "Image storage & moderation",
 "图片存储模式": "Image storage mode",
 "图片存储管理": "Image storage management",
 "图片对比": "Image comparison",
 "图片尺寸不足时自动放大": "Automatically upscale when the image is too small",
 "图片已删除": "Image deleted",
 "图片并发": "Image concurrency",
 "图片并发省略时默认 30，填写 0 表示不限；重复地址会自动跳过。": "If image concurrency is omitted it defaults to 30; enter 0 for unlimited. Duplicate addresses are skipped automatically.",
 "图片成功后删除官网会话": "Delete the official site conversation after image success",
 "图片接口": "Image API",
 "图片提示词": "Image prompt",
 "图片放大": "Image upscaling",
 "图片放大引擎": "Image upscaling engine",
 "图片文件目录": "Image file directory",
 "图片模型": "Image models",
 "图片没有可用于局部修改的地址": "The image has no address usable for local editing",
 "图片没有可读取的地址": "The image has no readable address",
 "图片流等待上限": "Image stream wait limit",
 "图片生成": "Image generation",
 "图片生成失败": "Image generation failed",
 "图片生成接口，支持 prompt、model、n、size、quality 等参数。": "Image generation endpoint; supports parameters such as prompt, model, n, size, and quality.",
 "图片确认": "Image confirmation",
 "图片管理": "Gallery",
 "图片管理加载失败": "Failed to load image management",
 "图片结果等待上限": "Image result wait limit",
 "图片编辑": "Image editing",
 "图片编辑任务提交失败": "Image edit task submission failed",
 "图片编辑接口，支持 multipart 上传参考图。": "Image editing endpoint; supports uploading reference images via multipart.",
 "图片自动清理": "Image auto-cleanup",
 "图片访问地址": "Image access URL",
 "图片轮询间隔": "Image polling interval",
 "图片重新生成失败": "Image regeneration failed",
 "图片链接已复制。": "Image link copied.",
 "图片预览": "Image preview",
 "图片额度": "Image quota",
 "图片首次轮询等待": "Initial image polling delay",
 "图生图": "Image to image",
 "在线更新失败，请稍后重试。": "Online update failed. Please try again later.",
 "基础信息": "Basic information",
 "基础端点": "Base endpoint",
 "基础配置": "Basic settings",
 "填入": "Fill in",
 "处理中": "Processing",
 "处理中...": "Working...",
 "备份中": "Backing up",
 "备份中...": "Backing up...",
 "备份内容": "Backup contents",
 "备份前缀": "Backup prefix",
 "备份已删除": "Backup deleted",
 "备份已删除，正在刷新历史...": "Backup deleted. Refreshing history...",
 "备份已完成，正在刷新历史...": "Backup complete. Refreshing history...",
 "备份连接不可用": "Backup connection unavailable",
 "备份连接可用": "Backup connection available",
 "备份连接测试失败": "Backup connection test failed",
 "备份连接测试通过": "Backup connection test passed",
 "备份间隔（分钟）": "Backup interval (minutes)",
 "备注": "Notes",
 "备用代理 URL": "Fallback proxy URL",
 "备用出口代理组": "Fallback egress proxy group",
 "备用出口模式": "Fallback egress mode",
 "复制": "Copy",
 "复制 AT": "Copy AT",
 "复制 OAuth 授权链接失败": "Failed to copy the OAuth authorization link",
 "复制 RT": "Copy RT",
 "复制图片链接失败。": "Failed to copy image link.",
 "复制失败": "Copy failed",
 "复制失败，请手动复制": "Copy failed. Please copy it manually.",
 "复制安装指令": "Copy install prompt",
 "复制成功": "Copied",
 "复制授权链接": "Copy authorization link",
 "复制链接": "Copy link",
 "复制链接失败。": "Failed to copy link.",
 "复制错误": "Copy error",
 "复制错误信息失败": "Failed to copy error message",
 "外部服务": "External services",
 "多": "More",
 "多个标签用逗号或空格分隔": "Separate multiple tags with commas or spaces",
 "失效时间": "Invalidated at",
 "失败": "Failed",
 "失败原因": "Failure reason",
 "失败时间": "Failed at",
 "套餐": "Plan",
 "存储模式": "Storage mode",
 "存储管理": "Storage",
 "安装指令不包含当前密钥；运行前设置 CHATGPT2API_API_KEY": "The install prompt does not include the current key; set CHATGPT2API_API_KEY before running it",
 "安装指令语言": "Install prompt language",
 "完成": "Completed",
 "完成导入": "Finish import",
 "完整备份会恢复凭据、配置与状态；已存在账号会覆盖更新。": "A full backup restores credentials, settings, and status; existing accounts are overwritten.",
 "完整账号 JSON": "full account JSON",
 "实例名称": "Instance name",
 "实时监控": "Live Monitor",
 "实时监控加载失败": "Failed to load live monitor",
 "实时监控明细": "Live monitor details",
 "审核提示词": "Review prompt",
 "容器内存": "Container memory",
 "密码": "Password",
 "密钥无效或已失效。": "The key is invalid or has expired.",
 "密钥由环境变量提供": "Key is provided by an environment variable",
 "对外错误": "Public error",
 "对比": "Compare",
 "对比位置": "Comparison position",
 "对比原图": "Compare with original",
 "对比模式": "Comparison mode",
 "对话": "Chat",
 "对话标题": "Chat title",
 "对话画图": "Chat & Image Studio",
 "对话请求失败": "Chat request failed",
 "对话重新生成失败": "Chat regeneration failed",
 "导入": "Import",
 "导入 / 添加": "Import / Add",
 "导入 Access Token": "Import Access Token",
 "导入 CPA JSON 文件": "Import CPA JSON file",
 "导入 Session JSON": "Import Session JSON",
 "导入 Sub2API JSON 文件": "Import Sub2API JSON file",
 "导入 Sub2API 账号": "Import Sub2API accounts",
 "导入中...": "Importing...",
 "导入完整备份文件": "Import full backup file",
 "导入账号": "Import accounts",
 "导入进度超时": "Import progress timed out",
 "导入远程 CPA": "Import remote CPA",
 "导入选中": "Import selected",
 "导出": "Export",
 "导出失败": "Export failed",
 "导出当前页摘要": "Export current page summary",
 "导航": "Navigation",
 "将尝试压缩本地图片以释放空间。该操作可能需要一点时间，确定继续吗？": "This will try to compress local images to free up space. It may take a while. Continue?",
 "将当前搜索接口安装为本地 Skill": "Install the current search endpoint as a local Skill",
 "将清理已过期图片的本地副本；仍有 WebDAV 副本的图库记录会保留。此操作不可恢复，确定继续吗？": "This will remove local copies of expired images; gallery records that still have a WebDAV copy are kept. This cannot be undone. Continue?",
 "将真实生成 1 张图片；成功后按现有账号规则扣除 1 次图片额度。": "This will actually generate 1 image; on success, 1 image quota is deducted under the existing account rules.",
 "小量 ¥0.02/张 · 中转 ¥0.01/张 · 大量/企业 ¥0.009/张": "Small volume ¥0.02/image · Relay ¥0.01/image · Bulk/enterprise ¥0.009/image",
 "少": "Less",
 "尚未测试": "Not tested yet",
 "局部": "Inpaint",
 "局部修改": "Edit region",
 "局部修改任务已提交": "Local edit task submitted",
 "局部修改图片读取失败": "Failed to read the image for local editing",
 "展开": "Expand",
 "展开任务面板": "Expand task panel",
 "展开侧边栏": "Expand sidebar",
 "展开全部": "Show all",
 "展开详情面板": "Expand details panel",
 "工作区滚动": "Scroll in workspace",
 "工具": "Tool",
 "已停止。": "Stopped.",
 "已启用": "Enabled",
 "已处理": "Processed",
 "已复制": "Copied",
 "已复制密钥": "Key copied",
 "已存在账号会更新凭据和配置。": "Existing accounts get their credentials and settings updated.",
 "已存在账号会更新凭据；导入后同步账号与额度。": "Existing accounts get their credentials updated; accounts and quota are synced after import.",
 "已完成": "Completed",
 "已开始下载": "Download started",
 "已引用到输入框": "Added to the input box",
 "已暂停": "Paused",
 "已有账号导入任务正在运行": "An account import task is already running",
 "已用空间": "Used space",
 "已禁用": "Disabled",
 "已耗时": "Elapsed",
 "已过期": "Expired",
 "已配置 API Key": "API Key configured",
 "已配置，留空不修改": "Configured; leave blank to keep unchanged",
 "常用接口": "Common endpoints",
 "平均成功耗时": "Avg. success duration",
 "平均耗时": "Avg. duration",
 "并排": "Side by side",
 "并排对比": "Side-by-side comparison",
 "应用 CPU": "App CPU",
 "应用内存": "App memory",
 "应用版本": "App version",
 "开启后顶部导航会显示画布入口，并自动带上当前接口地址和密钥。": "When enabled, the top navigation shows a canvas entry and automatically carries the current API address and key.",
 "开始刷新": "Start refresh",
 "开始压测或发起图片请求后，这里会实时出现运行中的调用。": "Running calls appear here in real time once you start a load test or send an image request.",
 "开始压缩": "Start compression",
 "开始同步": "Start sync",
 "开始处理": "Started",
 "开始备份": "Start backup",
 "开始导入": "Start import",
 "开始测试": "Start test",
 "开始清理": "Start cleanup",
 "异常": "Abnormal",
 "异常账号": "Abnormal accounts",
 "引用": "Reference",
 "引用到输入框": "Reference in composer",
 "引用图片读取失败": "Failed to read the image to reference",
 "张图片": "images",
 "强制直连": "Force direct connection",
 "当前": "Current",
 "当前代理": "Current proxy",
 "当前代理组有未保存的修改，关闭后这些内容将丢失。是否继续？": "This proxy group has unsaved changes that will be lost if you close it. Continue?",
 "当前代理组草稿": "Current proxy group draft",
 "当前占用": "Current usage",
 "当前容器启动后还没有图片相关请求完成。": "No image-related requests have completed since the current container started.",
 "当前并发": "Concurrent requests",
 "当前版本": "Current version",
 "当前筛选结果": "Current filter results",
 "当前范围内暂无可统计请求": "No countable requests in the current range",
 "当前范围内暂无成功耗时": "No successful request durations in the current range",
 "当前范围内暂无成功请求": "No successful requests in the current range",
 "当前范围内暂无模型耗时": "No model durations in the current range",
 "当前草稿": "Current draft",
 "当前视图": "Current view",
 "当前调用密钥": "Current API key",
 "当前账号强制直连，不需要测试代理": "This account uses a forced direct connection; there is no proxy to test",
 "待处理": "Remaining",
 "总数": "Total",
 "总耗时": "Total time",
 "总调用量": "Total calls",
 "恢复时间": "Restored",
 "慢请求": "Slow Requests",
 "成功": "Success",
 "成功 / 失败": "Success / Failure",
 "成功率": "Success rate",
 "成功耗时趋势": "Success duration trend",
 "成功耗时趋势时间范围": "Success duration trend time range",
 "手动添加账号": "Add account manually",
 "打开": "Open",
 "打开会话列表": "Open conversation list",
 "打开发布页": "Open release page",
 "打开导航": "Open navigation",
 "打开授权页面": "Open authorization page",
 "打开无限画布": "Open infinite canvas",
 "执行": "Execution",
 "执行备份失败": "Backup failed",
 "执行立即备份": "run a backup now",
 "批量下载": "Download selected",
 "批量下载图片": "Download images",
 "批量下载失败": "Batch download failed",
 "批量删除": "Delete selected",
 "批量删除图片": "Delete images",
 "批量删除失败": "Batch delete failed",
 "批量删除日志": "Delete logs",
 "批量删除账号": "Delete accounts in bulk",
 "批量刷新 AT": "Refresh AT in bulk",
 "批量同步账号与额度": "Sync accounts and quota in bulk",
 "批量启用": "Enable in bulk",
 "批量启用账号": "Enable accounts in bulk",
 "批量处理": "Bulk actions",
 "批量添加": "Add nodes",
 "批量添加代理节点": "Bulk add proxy nodes",
 "批量添加代理节点失败": "Failed to bulk add proxy nodes",
 "批量添加节点": "Bulk add nodes",
 "批量禁用": "Disable in bulk",
 "批量禁用账号": "Disable accounts in bulk",
 "批量绑定账号组": "Bind account group in bulk",
 "批量绑定账号组失败": "Failed to bind account group in bulk",
 "找到图片结果后再等待指定秒数复查一次，减少结果尚未稳定时提前返回。": "After an image result is found, wait the specified number of seconds and check once more, reducing early returns before the result has stabilized.",
 "拖动调整历史栏宽度": "Drag to resize the history sidebar",
 "按任务 ID 查询 PPT/PSD 文件生成状态。": "Queries the generation status of PPT/PSD files by task ID.",
 "按原版模块分组维护系统配置。": "Manage system configuration, grouped by the original modules.",
 "按执行顺序展示，条形长度表示相对耗时": "Shown in execution order; bar length indicates relative duration",
 "按目标剩余空间清理": "Clean up to a target free space",
 "按目标剩余空间清理失败": "Failed to clean up to target free space",
 "按等待入口、等待账号、等待出口、上游生成和上游断流综合排序。": "Ranked by combined time waiting for entry, account, and egress, plus upstream generation and upstream stream interruptions.",
 "按远端分组导入": "Import by remote group",
 "换一个关键词、来源或分类再试。": "Try a different keyword, source, or category.",
 "换个筛选条件或刷新后再看。": "Try different filters or refresh.",
 "授权链接已复制": "Authorization link copied",
 "授权链接已生成。登录完成后，把浏览器最终跳转到的 callback URL 粘贴到下方。": "Authorization link generated. After signing in, paste the callback URL the browser finally redirects to below.",
 "接口": "Endpoint",
 "接口信息": "API info",
 "接口接入": "API access",
 "控制台日志级别": "Console log level",
 "控制台登录": "Console sign-in",
 "控制台请求超时": "Console request timeout",
 "控制账号批量任务的最大并发数。刷新 AT、同步账号与额度、导入核验和后台复查按账号占用并发；启用、禁用、重置、删除和批量保存按整个批次占用一个并发。默认 30，可设置为 1–100；图片生成并发单独设置。": "Controls the maximum concurrency of account batch tasks. Refreshing AT, syncing accounts and quotas, import verification, and background rechecks use one concurrency slot per account; enabling, disabling, resetting, deleting, and batch saving use one slot for the whole batch. Defaults to 30; can be set to 1–100. Image generation concurrency is configured separately.",
 "推理": "Reasoning",
 "推送到 GenBox": "Push to GenBox",
 "推送到 GenBox 失败": "Failed to push to GenBox",
 "描述你想如何修改参考图": "Describe how you want to edit the reference images",
 "描述你想让模型识别或分析的图片": "Describe what you want the model to recognize or analyze in the images",
 "描述局部修改要求": "Describe the edit you want",
 "提交 PPT 或 PSD 后，任务会显示在这里。": "Tasks appear here after you submit a PPT or PSD.",
 "提交修改": "Submit edit",
 "提交图片任务": "Submit image task",
 "提示词": "Prompts",
 "提示词分类": "Prompt category",
 "提示词加载失败": "Failed to load prompts",
 "提示词加载失败，请稍后重试。": "Failed to load prompts. Please try again later.",
 "提示词库": "Prompt library",
 "提示词库响应中的同步摘要无效。": "Invalid sync summary in the prompt library response.",
 "提示词库响应中的词源计数无效。": "Invalid source count in the prompt library response.",
 "提示词库响应包含无效提示词。": "Prompt library response contains an invalid prompt.",
 "提示词库响应包含无效词源。": "Prompt library response contains an invalid source.",
 "提示词库响应版本不受支持，请确认前后端版本一致。": "Unsupported prompt library response version. Make sure the frontend and backend versions match.",
 "提示词库响应缺少 items、sources 或 source_errors。": "Prompt library response is missing items, sources, or source_errors.",
 "提示词库响应缺少 revision。": "Prompt library response is missing revision.",
 "提示词来源": "Prompt source",
 "提示词源": "Prompt sources",
 "提示词源已停用": "Prompt source disabled",
 "提示词源已启用": "Prompt source enabled",
 "提示词源更新失败": "Failed to update prompt source",
 "提示词源正在更新，请稍后再试。": "The prompt source is being updated. Please try again later.",
 "搜索": "Search",
 "搜索 Skill": "Search Skill",
 "搜索代理组 / 节点 / 地址": "Search proxy groups / nodes / addresses",
 "搜索关键词、账号、错误码": "Search keywords, accounts, error codes",
 "搜索完成，但上游没有返回摘要。": "Search completed, but upstream returned no summary.",
 "搜索对话": "Search chats",
 "搜索文件名、路径、标签": "Search filename, path, tags",
 "搜索标题、分类、词源或提示词": "Search by title, category, source, or prompt",
 "搜索请求失败": "Search request failed",
 "搜索账号 ID / 邮箱 / Token / 套餐 / 来源": "Search account ID / email / token / plan / source",
 "搜索重新请求失败": "Search re-request failed",
 "撤销": "Undo",
 "撤销上一步": "Undo last step",
 "操作": "Actions",
 "支持模型": "Supported models",
 "支持直接粘贴，一行一个；也支持从 TXT 文件读取，一行一个。": "Paste tokens directly, one per line, or read them from a TXT file, one per line.",
 "收起": "Collapse",
 "收起任务面板": "Collapse task panel",
 "收起侧边栏": "Collapse sidebar",
 "收起详情面板": "Collapse details panel",
 "放大引擎": "Upscaling engine",
 "放弃代理组草稿": "Discard proxy group draft",
 "放弃修改": "Discard changes",
 "敏感词": "Sensitive words",
 "数据盘": "Data disk",
 "数量": "Count",
 "文件": "File",
 "文件下载": "File download",
 "文件下载失败": "File download failed",
 "文件任务加载失败": "Failed to load file tasks",
 "文件任务已删除": "File task deleted",
 "文件任务已过期或不存在": "The file task has expired or does not exist",
 "文件任务提交失败": "File task submission failed",
 "文件任务重新提交失败": "File task resubmission failed",
 "文件生成失败，请稍后重试。": "File generation failed. Please try again later.",
 "文本": "Text",
 "文生图": "Text to image",
 "新图": "New",
 "新图没有可用于对比的地址": "The new image has no address usable for comparison",
 "新增": "Add",
 "新增 CPA 连接": "Add CPA connection",
 "新增 CPA 连接需要管理密钥": "A management key is required for a new CPA connection",
 "新增 Sub2API 连接": "Add Sub2API connection",
 "新增 Sub2API 连接需要邮箱密码或 Admin API Key": "An email and password or an Admin API Key is required for a new Sub2API connection",
 "新密钥只展示一次，请现在复制保存。": "New keys are shown only once. Copy and save it now.",
 "新对话": "New chat",
 "新建代理组": "New proxy group",
 "新建代理组后，可绑定账号组、账号或默认出口使用。": "After you create a proxy group, you can bind it to an account group, an account, or the default egress.",
 "新建账号组": "New account group",
 "新打开概览中心时，各图表默认使用这个统计周期；进入页面后仍可单独切换。": "When the overview center is first opened, all charts use this statistics period by default; you can still switch each one after entering the page.",
 "新的专用密钥（可选）": "New dedicated key (optional)",
 "无图片 URL": "No image URL",
 "无法读取图片文件": "Unable to read the image file",
 "无法连接后端检查更新，请稍后重试。": "Unable to reach the backend to check for updates. Please try again later.",
 "无法预览": "Preview unavailable",
 "无限画布": "Infinite canvas",
 "无限画布地址": "Infinite canvas URL",
 "日志加载失败": "Failed to load logs",
 "日志已删除": "Log deleted",
 "日志管理": "Logs",
 "日志结果图片": "Log result image",
 "日志自动清理": "Log auto-cleanup",
 "日志详情": "Log details",
 "日志详情加载失败": "Failed to load log details",
 "早期连接失败时重试直连一次。": "Retry once with a direct connection on early connection failure.",
 "时间": "Time",
 "是否立即删除这些过期数据？": "Delete this expired data now?",
 "是否立即移除这些账号？正常账号不会受影响。": "Remove these accounts now? Healthy accounts will not be affected.",
 "显示": "Show",
 "显示或隐藏选区": "Show or hide selection",
 "普通用户": "Regular user",
 "暂停刷新": "Pause refresh",
 "暂无 CPA 连接。": "No CPA connections yet.",
 "暂无 Sub2API 连接。": "No Sub2API connections yet.",
 "暂无代理组": "No proxy groups",
 "暂无任务记录": "No task log entries",
 "暂无可导入文件": "No files to import",
 "暂无可导入账号": "No accounts to import",
 "暂无可导出的账号": "No accounts to export",
 "暂无图片": "No images",
 "暂无完成记录": "No completed records",
 "暂无已有标签": "No existing tags",
 "暂无慢请求": "No slow requests",
 "暂无提示词源。": "No prompt sources yet.",
 "暂无数据": "No data",
 "暂无文件任务": "No file tasks",
 "暂无日志": "No logs",
 "暂无普通用户密钥。创建后可以分发给只需要画图入口的用户。": "No regular user keys yet. Once created, they can be handed out to users who only need the image page.",
 "暂无更新日志。": "No changelog available.",
 "暂无本地提示词": "No local prompts",
 "暂无活跃请求": "No active requests",
 "暂无账号数据": "No account data",
 "暂无阶段记录": "No stage records",
 "更多": "More",
 "更多条件": "More conditions",
 "更新": "Update",
 "更新中...": "Updating...",
 "更新提示词快照": "Update prompt snapshot",
 "更新本地快照": "Update local snapshot",
 "更新用户密钥失败": "Failed to update user key",
 "更新账号组失败": "Failed to update account group",
 "最多只能添加 8 张参考图": "You can add at most 8 reference images",
 "最大尝试账号数": "Maximum accounts to try",
 "最新": "Latest",
 "最新版本": "Latest version",
 "最新统计刷新失败，当前展示最近一次可用快照。": "Failed to refresh the latest statistics; showing the latest available snapshot.",
 "最近": "Recent",
 "最近失败": "Last failed",
 "最近完成": "Recently Completed",
 "最近完成的图片相关调用，窗口保存在进程内存中。": "Recently completed image-related calls; the window is kept in process memory.",
 "最近对象": "Last object",
 "最近开始": "Last started",
 "最近成功": "Last succeeded",
 "最近成功刷新 AT": "Last successful AT refresh",
 "最近文件任务": "Recent file tasks",
 "最近文件任务加载失败": "Failed to load recent file tasks",
 "最近状态": "Last status",
 "最近错误": "Last error",
 "有 access token": "Has access token",
 "服务": "Services",
 "服务启动": "Service started",
 "服务地址": "Service URL",
 "服务运行": "Service uptime",
 "未分组": "Ungrouped",
 "未分组账号": "Ungrouped accounts",
 "未加载": "Not loaded",
 "未发布": "Unreleased",
 "未同步": "Not synced",
 "未启用": "Not enabled",
 "未启用备用出口。": "Fallback egress is not enabled.",
 "未命名对话": "Untitled chat",
 "未填邮箱": "No email set",
 "未开始导入": "Import not started",
 "未执行": "Not run",
 "未指定账号或账号组代理时直连。": "Connects directly when no account or account group proxy is specified.",
 "未标记区域尽量保持与第一张原图一致。": "Keep unmarked areas as consistent with the first original image as possible.",
 "未检查": "Not checked",
 "未生成": "Not generated",
 "未登录": "Not logged in",
 "未知": "Unknown",
 "未获取": "Not available",
 "未获取到系统配置，请重新加载。": "Could not retrieve the system configuration. Please reload.",
 "未设置": "Not set",
 "未配置 API Key": "API Key not configured",
 "本地": "Local",
 "本地 + WebDAV": "Local + WebDAV",
 "本地 → WebDAV": "Local → WebDAV",
 "本地+云": "Local + cloud",
 "本地搜索兼容入口，返回 answer 与 sources。": "Local search-compatible endpoint; returns answer and sources.",
 "本次导入有同步失败，但没有确认失效账号；暂时检测失败的账号会保留": "Some accounts failed to sync in this import, but none are confirmed invalid; accounts that could not be checked for now will be kept",
 "本页图片": "Page images",
 "本页失败": "Page failed",
 "本页总数": "Page total",
 "本页成功": "Page success",
 "本页文本": "Page text",
 "本页限流": "Page limited",
 "条": "items",
 "条件": "Conditions",
 "条日志": "logs",
 "来源": "Source",
 "来源 / 套餐": "Source / Plan",
 "来源 ID": "Source ID",
 "松开以添加参考图": "Drop to add reference images",
 "查看": "View",
 "查看图片占用、磁盘剩余空间，并执行简单清理。": "View image usage and free disk space, and run simple cleanups.",
 "查看图片预览": "View image preview",
 "查看当前版本和更新日志": "View the current version and changelog",
 "查看接口信息": "View API info",
 "查看版本更新": "View version updates",
 "查看详情": "View details",
 "查询可编辑文件任务": "Query editable file tasks",
 "标签": "Tags",
 "标签已保存。": "Tags saved.",
 "标记图生成失败": "Failed to generate the mask image",
 "核对已选账号数量失败": "Failed to verify the selected account count",
 "根据客户端选择对应接口": "Choose the endpoint that matches your client",
 "根路径": "Root path",
 "格式错误": "Format errors",
 "检查中": "Checking",
 "检查中...": "Checking...",
 "检查更新": "Check for updates",
 "检查本次确认失效账号失败，已先保留": "Failed to check which accounts from this import are confirmed invalid; keeping them for now",
 "检测": "Test",
 "检测中...": "Testing...",
 "检测代理组节点": "Check proxy group nodes",
 "检测全部节点": "Test all nodes",
 "检测到可清理数据": "Cleanable data detected",
 "检测到可移除账号": "Removable accounts detected",
 "检测失败": "Test failed",
 "概览中心": "Overview",
 "概览中心默认统计周期": "Overview center default statistics period",
 "概览加载失败": "Failed to load overview",
 "模型": "Model",
 "模型列表": "Model list",
 "模型耗时": "Model duration",
 "模型耗时时间范围": "Model duration time range",
 "模型请求分布": "Model request distribution",
 "模型请求分布时间范围": "Model request distribution time range",
 "正在从 image-prompts 下载并更新本地快照...": "Downloading from image-prompts and updating the local snapshot...",
 "正在准备页面内容...": "Preparing page content...",
 "正在创建任务": "Creating task",
 "正在删除备份文件...": "Deleting backup file...",
 "正在加载": "Loading",
 "正在加载...": "Loading...",
 "正在加载代理": "Loading proxies",
 "正在加载图片": "Loading images",
 "正在加载日志": "Loading logs",
 "正在加载日志详情": "Loading log details",
 "正在加载概览": "Loading overview",
 "正在加载用户密钥": "Loading user keys",
 "正在加载设置": "Loading settings",
 "正在加载账号": "Loading accounts",
 "正在压缩图片...": "Compressing images...",
 "正在回复": "Replying",
 "正在处理图片": "Processing image",
 "正在打包 ZIP...": "Packing ZIP...",
 "正在打包并上传运行数据...": "Packaging and uploading runtime data...",
 "正在扫描并上传本地图片...": "Scanning and uploading local images...",
 "正在推送 GenBox": "Pushing to GenBox",
 "正在提交": "Submitting",
 "正在提交删除请求...": "Submitting delete request...",
 "正在提交图片": "Submitting image",
 "正在提交批量删除请求...": "Submitting batch delete request...",
 "正在提交文件任务": "Submitting file task",
 "正在搜索": "Searching",
 "正在搜索...": "Searching...",
 "正在整理阶段时间线...": "Preparing the stage timeline...",
 "正在更新 ChatGPT2API": "Updating ChatGPT2API",
 "正在检查云端版本...": "Checking the cloud version...",
 "正在测试账号": "Testing account",
 "正在清理到目标剩余空间...": "Cleaning up to target free space...",
 "正在清理过期图片...": "Cleaning up expired images...",
 "正在生成可编辑文件": "Generating editable file",
 "正在编辑原消息，发送后会替换该消息并重新生成后续回复。": "Editing the original message. Sending will replace it and regenerate the replies that follow.",
 "正在获取实时快照": "Fetching live snapshot",
 "正在获取最新日志数据。": "Fetching the latest log data.",
 "正在解析并去重...": "Parsing and removing duplicates...",
 "正在请求": "Sending request",
 "正在读取下载地址": "Loading download link",
 "正在读取完整日志数据...": "Reading the full log data...",
 "正在读取当前进程的活跃请求、完成记录和瓶颈诊断。": "Reading active requests, completed records, and bottleneck diagnostics from the current process.",
 "正在读取接口": "Loading endpoint",
 "正在读取提示词源": "Loading prompt sources",
 "正在读取文件任务": "Loading file tasks",
 "正在读取最近任务": "Loading recent tasks",
 "正在读取本地快照": "Loading local snapshot",
 "正在读取本地提示词": "Loading local prompts",
 "正在读取请求详情": "Loading request details",
 "正在运行的图片请求，按进入时间排序。": "Image requests currently running, sorted by arrival time.",
 "正在预估可清理图片...": "Estimating images to clean up...",
 "正常": "Normal",
 "正常账号": "Active accounts",
 "步骤明细": "Step breakdown",
 "步骤耗时": "Step timings",
 "每次请求都会作为 system 消息注入。": "Injected as a system message on every request.",
 "每行一个代理地址，可在地址后填写图片并发": "One proxy address per line; optionally add image concurrency after the address",
 "每行格式：代理地址 图片并发": "Format per line: proxy address image concurrency",
 "比例": "Aspect ratio",
 "没有匹配的对话": "No matching chats",
 "没有匹配的提示词": "No matching prompts",
 "没有可导入的 access token": "No access tokens to import",
 "没有可操作的账号": "No accounts available to operate on",
 "没有可添加的代理节点": "No proxy nodes to add",
 "没有获取到导入结果": "No import result was returned",
 "活跃请求": "Active Requests",
 "浅色": "Light",
 "测试": "Test",
 "测试 CPA 连接": "Test CPA connection",
 "测试 Sub2API 连接": "Test Sub2API connection",
 "测试 WebDAV": "Test WebDAV",
 "测试中": "Testing",
 "测试中...": "Testing...",
 "测试代理失败": "Proxy test failed",
 "测试备份连接": "test the backup connection",
 "测试当前代理": "Test current proxy",
 "测试模型": "Test model",
 "测试类型": "Test type",
 "测试结果将在这里显示": "Test results will appear here",
 "测试账号": "Test account",
 "测试连接": "Test connection",
 "测试默认出口": "Test default egress",
 "浏览器不支持标记画布": "Your browser does not support the mask canvas",
 "浏览器不支持流式响应": "Your browser does not support streaming responses",
 "深色": "Dark",
 "添加中...": "Adding...",
 "添加到草稿，保存代理组后生效": "Added to the draft; takes effect after you save the proxy group",
 "添加节点": "Add node",
 "添加账号": "Add account",
 "清理到目标": "Clean up to target",
 "清理到目标空间": "Clean up to target space",
 "清理失败": "Cleanup failed",
 "清理完成": "Cleanup complete",
 "清理过期": "Clean up expired",
 "清理过期图片": "Clean up expired images",
 "清理过期图片失败": "Failed to clean up expired images",
 "清空": "Clear",
 "清空历史": "Clear history",
 "清空历史记录": "Clear history",
 "清空当前对话": "Clear current conversation",
 "清空本组": "Clear group",
 "清空选区": "Clear selection",
 "滑杆": "Slider",
 "滑杆对比": "Slider comparison",
 "滚动到最新消息": "Scroll to latest message",
 "演示数据": "Demo data",
 "演示模型": "Demo model",
 "点击展开": "Click to expand",
 "版本": "Version",
 "版本更新": "Version updates",
 "状态": "Status",
 "状态筛选": "Filter by status",
 "状态详情": "Status details",
 "状态说明": "Status description",
 "生图 API": "Image generation API",
 "生图失败后尝试其他账号": "Try other accounts after image generation fails",
 "生成": "Generate",
 "生成 OAuth 授权链接失败": "Failed to generate the OAuth authorization link",
 "生成图片": "Generated image",
 "生成图片.png": "generated-image.png",
 "生成尝试": "Generation attempts",
 "生成并打开授权页面": "Generate and open authorization page",
 "用于生成图片结果的访问前缀地址。": "URL prefix used to build access links for generated images.",
 "用于账号管理里的 Sub2API 远程导入。": "Used for Sub2API remote import in account management.",
 "用于账号管理里的远程 CPA 导入。": "Used for remote CPA import in account management.",
 "用户名": "Username",
 "用户名称已更新": "User name updated",
 "用户密钥": "User keys",
 "用户密钥已创建": "User key created",
 "用户密钥已删除": "User key deleted",
 "用户密钥已启用": "User key enabled",
 "用户密钥已更新": "User key updated",
 "用户密钥已禁用": "User key disabled",
 "用户密钥管理": "User key management",
 "用浏览器登录 ChatGPT，回填 callback URL 后保存 RT，用于 AT 临期自动续期。": "Sign in to ChatGPT in your browser, paste the callback URL back here, and the RT is saved so the AT can be renewed automatically before it expires.",
 "画图": "Image",
 "画布": "Canvas",
 "画笔": "Brush",
 "留空": "Leave blank",
 "留空则不修改密码": "Leave blank to keep the password unchanged",
 "留空则不修改密钥": "Leave blank to keep the key unchanged",
 "留空则不修改当前密钥": "Leave blank to keep the current key",
 "留空表示不修改": "Leave blank to keep unchanged",
 "留空表示未知": "Leave blank if unknown",
 "留空表示未知（Free / Plus / Pro）": "Leave blank if unknown (Free / Plus / Pro)",
 "登录": "Sign in",
 "登录中...": "Signing in...",
 "登录失败，请检查密码。": "Sign-in failed. Please check your password.",
 "目标分组": "Target group",
 "目标版本": "Target version",
 "直接创建 PPT 生成任务，返回任务 ID 后再查询状态。": "Creates a PPT generation task directly; query its status with the returned task ID.",
 "直接创建 PSD 生成任务，返回任务 ID 后再查询状态。": "Creates a PSD generation task directly; query its status with the returned task ID.",
 "直连": "Direct",
 "直连模式无需测试出口": "Direct mode does not need an egress test",
 "知道了": "Got it",
 "矩形": "Rectangle",
 "确定": "Confirm",
 "确定清空本地对话画图历史吗？已生成的图片文件不会删除。": "Clear the local chat and image history? Generated image files will not be deleted.",
 "确认 Sub2API 导入": "Confirm Sub2API import",
 "确认保存出口配置": "Confirm saving egress settings",
 "确认保存系统设置": "Confirm saving system settings",
 "确认停用代理组": "Confirm disabling proxy group",
 "确认删除": "Confirm delete",
 "确认删除这条日志？": "Delete this log?",
 "确认同步图片存储": "Confirm image storage sync",
 "确认启用": "Confirm enable",
 "确认启用代理组": "Confirm enabling proxy group",
 "确认导入": "Confirm import",
 "确认操作": "Confirm action",
 "确认更新": "Confirm update",
 "确认测试 WebDAV": "Confirm WebDAV test",
 "确认测试代理组": "Confirm proxy group test",
 "确认测试代理节点": "Confirm proxy node test",
 "确认测试备份连接": "Confirm backup connection test",
 "确认测试账号代理": "Confirm account proxy test",
 "确认测试默认出口": "Confirm default egress test",
 "确认禁用": "Confirm disable",
 "确认立即备份": "Confirm backup now",
 "确认绑定": "Confirm bind",
 "确认远程 CPA 导入": "Confirm remote CPA import",
 "确认鉴权无效的账号会进入异常处理；开启后直接移除，关闭后保留异常状态。": "Accounts whose authentication is confirmed invalid enter abnormal handling. When enabled they are removed directly; when disabled they keep the abnormal status.",
 "磁盘与图库": "Disk & gallery",
 "磁盘使用率": "Disk usage",
 "磁盘剩余": "Free disk space",
 "磁盘总量": "Total disk",
 "禁用": "Disabled",
 "禁用账号": "Disabled accounts",
 "秒": "sec",
 "移除本次确认失效账号失败": "Failed to remove accounts confirmed invalid in this import",
 "移除本次确认失效账号？": "Remove accounts confirmed invalid in this import?",
 "稍后处理": "Later",
 "空对话": "Empty chat",
 "窗口 0 / 0": "Window 0 / 0",
 "窗口内没有可排序的完成请求。": "No completed requests in the window can be ranked.",
 "立即刷新": "Refresh now",
 "立即备份": "Back up now",
 "立即更新": "Update now",
 "立即清理": "Clean up now",
 "立即移除": "Remove now",
 "第三方应用按 OpenAI 兼容接口接入，使用同一套 Bearer 鉴权。": "Third-party apps connect through the OpenAI-compatible API and use the same Bearer authentication.",
 "等待任务记录...": "Waiting for task log...",
 "等待开始生成": "Waiting to start generation",
 "等待确认": "Waiting for confirmation",
 "筛选": "Filter",
 "签发时间": "Issued at",
 "管理 ID": "Management ID",
 "管理员密码": "Admin password",
 "管理员登录密钥继续从部署配置读取，不在此页面展示；如需分发给其他人，请到“用户密钥”创建普通用户密钥。": "The admin login key is still read from the deployment configuration and is not shown on this page. To share access with others, create a regular user key under \"User keys\".",
 "管理员邮箱": "Admin email",
 "管理密钥": "Admin key",
 "类型": "Type",
 "粘贴 refresh token": "Paste the refresh token",
 "粘贴完整 access token": "Paste the full access token",
 "粘贴完整 callback URL，或只粘贴 code": "Paste the full callback URL, or just the code",
 "粘贴完整 session JSON": "Paste the full session JSON",
 "系统": "System",
 "系统内存": "System memory",
 "系统发行版": "OS distribution",
 "系统设置": "Settings",
 "绑定分组": "Bind group",
 "结果": "Result",
 "结果 URL": "Result URLs",
 "统一创建 PPT/PSD 文件任务，kind 可填 ppt 或 psd。": "Creates a PPT/PSD file task through a unified endpoint; set kind to ppt or psd.",
 "统计数据暂未更新，当前展示最近一次可用快照。": "Statistics have not been updated yet; showing the latest available snapshot.",
 "继续任务": "Resume task",
 "继续刷新": "Resume refresh",
 "继续图片任务失败": "Failed to resume image tasks",
 "继续编辑": "Keep editing",
 "编辑": "Edit",
 "编辑 CPA 连接": "Edit CPA connection",
 "编辑 Sub2API 连接": "Edit Sub2API connection",
 "编辑代理组": "Edit proxy group",
 "编辑标签": "Edit tags",
 "编辑用户密钥": "Edit user key",
 "编辑账号": "Edit account",
 "编辑账号组": "Edit account group",
 "羽化": "Feather",
 "耗时": "Duration",
 "聊天模型": "Chat models",
 "聊天补全": "Chat completions",
 "联网搜索": "Web search",
 "自动": "Auto",
 "自动删除多少小时前的控制台调用日志。": "Automatically delete console call logs older than this many hours.",
 "自动删除多少小时前的本地图片。": "Automatically delete local images older than this many hours.",
 "自动刷新": "Auto refresh",
 "自动刷新间隔（秒）": "Auto-refresh interval (seconds)",
 "自动模型": "Auto model",
 "自动移除异常账号": "Automatically remove abnormal accounts",
 "自动移除额度耗尽账号": "Automatically remove accounts with exhausted quota",
 "自定义代理": "Custom proxy",
 "自定义代理 URL": "Custom proxy URL",
 "自定义代理：未填写": "Custom proxy: not entered",
 "自建 Sub2API": "Self-hosted Sub2API",
 "至": "to",
 "节点": "Nodes",
 "节点检测失败": "Node check failed",
 "获取当前密钥最近提交的 PPT 与 PSD 任务。": "Fetching the PPT and PSD tasks most recently submitted with the current key.",
 "解析 Session JSON 失败": "Failed to parse the Session JSON",
 "触发切号": "Account switches",
 "设为直连": "Use direct connection",
 "设置": "Settings",
 "设置保存成功": "Settings saved",
 "设置分组": "Settings groups",
 "设置加载失败": "Failed to load settings",
 "设置基线尚未加载，请刷新设置后重试": "The settings baseline has not loaded yet. Refresh the settings and try again",
 "设置尚未加载，请刷新设置后重试": "Settings have not loaded yet. Refresh the settings and try again",
 "设置版本尚未加载，请刷新设置后重试": "Settings version has not loaded yet. Refresh settings and try again.",
 "诊断字段": "Diagnostic fields",
 "该请求没有保留可展示的阶段事件。": "This request has no stage events to display.",
 "该请求没有可展示的步骤耗时。": "No step timings available for this request.",
 "该账号不单独指定代理，会按账号组代理、默认出口顺序回退。": "This account has no proxy of its own; it falls back to the account group proxy, then the default egress.",
 "该账号强制直连，不读取账号组或默认出口。": "This account is forced to connect directly and does not use the account group or default egress.",
 "该账号组强制直连，组内账号不会回退默认出口。": "This account group is forced to connect directly; its accounts do not fall back to the default egress.",
 "请先填写自定义代理地址": "Enter a custom proxy address first",
 "请先生成 OAuth 授权链接": "Generate an OAuth authorization link first",
 "请先粘贴 Session JSON": "Paste the Session JSON first",
 "请先粘贴 callback URL 或 code": "Paste the callback URL or code first",
 "请先选择 CPA 连接": "Select a CPA connection first",
 "请先选择 Sub2API 连接": "Select a Sub2API connection first",
 "请先选择代理组": "Select a proxy group first",
 "请先选择要导出的账号": "Select accounts to export first",
 "请先选择要绑定的账号组": "Select an account group to bind first",
 "请先选择账号": "Select accounts first",
 "请到系统设置的提示词源里更新一次词源。": "Update the prompt sources once under Settings > Prompt sources.",
 "请填写 access token": "Enter an access token",
 "请填写代理组名称": "Enter a proxy group name",
 "请填写备用代理 URL": "Enter a fallback proxy URL",
 "请填写自定义代理 URL": "Enter a custom proxy URL",
 "请填写账号组名称": "Enter an account group name",
 "请填写账号组自定义代理地址": "Enter a custom proxy address for the account group",
 "请求": "Request",
 "请求与任务": "Requests and tasks",
 "请求失败": "Request failed",
 "请求失败，请稍后重试。": "Request failed. Please try again later.",
 "请求头": "Request header",
 "请求头使用 Authorization: Bearer <当前调用密钥>。": "Request header: Authorization: Bearer <current API key>.",
 "请求文本": "Request text",
 "请求文本（已截断）": "Request text (truncated)",
 "请求详情": "Request details",
 "请求详情加载失败": "Failed to load request details",
 "请求超时（秒）": "Request timeout (seconds)",
 "请求身份": "Request identity",
 "请等待当前账号任务完成": "Wait for the current account task to finish",
 "请等待当前账号导入任务完成": "Wait for the current account import task to finish",
 "请至少填写一个代理节点地址": "Enter at least one proxy node address",
 "请输入 CPA 地址": "Enter the CPA address",
 "请输入 GenBox Push Key": "Enter the GenBox Push Key",
 "请输入 Secret Access Key": "Enter the Secret Access Key",
 "请输入 Sub2API 地址": "Enter the Sub2API address",
 "请输入 WebDAV 密码": "Enter the WebDAV password",
 "请输入数值": "Enter a number",
 "请输入整数": "Enter a whole number",
 "请输入有效数值": "Enter a valid number",
 "请输入有效的目标剩余空间。": "Enter a valid target free space.",
 "请选择 CPA 连接": "Select a CPA connection",
 "请选择 Sub2API 连接": "Select a Sub2API connection",
 "请选择备用出口代理组": "Select a fallback egress proxy group",
 "请选择账号组默认代理组": "Select a default proxy group for the account group",
 "请选择默认出口代理组": "Select a default egress proxy group",
 "请重新上传原图后提交文件任务": "Re-upload the original image before submitting the file task",
 "读取 Access Token 文件失败": "Failed to read the Access Token file",
 "读取 Sub2API 导出的 JSON 文件，提取账号凭据并同步账号信息与额度。": "Reads a JSON file exported from Sub2API, extracts the account credentials, and syncs account info and quota.",
 "读取 TXT 文件": "Read TXT file",
 "读取代理组、节点和健康状态。": "Reading proxy groups, nodes, and health status.",
 "读取凭据": "Reading credentials",
 "读取到的内容不是图片": "The content that was read is not an image",
 "读取到的图片为空": "The image that was read is empty",
 "读取参考图失败": "Failed to read reference image",
 "读取图片记录、标签和分页数据。": "Reading image records, tags, and pagination data.",
 "读取已保存 CPA 连接中的账号文件。": "Read account files from a saved CPA connection.",
 "读取已保存 CPA 连接里的账号文件，勾选后导入本地号池。": "Reads account files from the saved CPA connection. Select them to import into the local pool.",
 "读取已保存 Sub2API 连接中的 OpenAI 账号。": "Read OpenAI accounts from a saved Sub2API connection.",
 "读取已保存 Sub2API 连接里的账号；选择“全部账号”时会按远端分组折叠加载，导入时可自动创建或复用同名本地分组。": "Reads accounts from the saved Sub2API connection. When \"All accounts\" is selected, accounts are loaded grouped by remote group, and same-named local groups can be created or reused on import.",
 "读取普通用户密钥列表。": "Reading the list of regular user keys.",
 "读取最新账号和调用数据。": "Reading the latest account and call data.",
 "读取本系统导出的完整账号 JSON，直接恢复已保存的凭据和账号配置，不请求远程接口验证。": "Reads a full account JSON exported by this system and restores the saved credentials and account settings directly, without verifying against a remote API.",
 "读取系统配置、存储配置和外部连接。": "Reading system configuration, storage configuration, and external connections.",
 "读取账号列表、分组和分页状态。": "Reading the account list, groups, and pagination state.",
 "调用": "Calls",
 "调用日志": "Call logs",
 "调用概览": "Call overview",
 "调用活跃度": "Call activity",
 "调用活跃度时间范围": "Call activity time range",
 "调用结果趋势": "Call result trend",
 "调用结果趋势时间范围": "Call result trend time range",
 "账号": "Account",
 "账号 / 出口": "Account / Egress",
 "账号任务记录": "Account task log",
 "账号凭据": "Account credentials",
 "账号尝试": "Account attempts",
 "账号已添加": "Account added",
 "账号总数": "Total accounts",
 "账号批量任务并发": "Account batch task concurrency",
 "账号操作响应缺少后端展示投影": "Account action response is missing the backend display projection",
 "账号操作响应缺少进度投影": "Account operation response is missing the progress projection",
 "账号操作超时，请稍后重新打开列表查看结果": "Account operation timed out. Reopen the list later to check the result.",
 "账号日志": "Account logs",
 "账号未记录": "Account not recorded",
 "账号来源": "Account source",
 "账号校验失败并已自动移除": "Account validation failed and the account was removed automatically",
 "账号概览": "Account overview",
 "账号测试失败": "Account test failed",
 "账号状态筛选": "Filter accounts by status",
 "账号策略": "Account policy",
 "账号管理": "Accounts",
 "账号管理页的远程导入会读取这里保存的连接。": "The remote import on the Accounts page reads the connections saved here.",
 "账号组": "Account group",
 "账号组不单独指定代理，组内账号会继续回退默认出口。": "The account group has no proxy of its own; its accounts keep falling back to the default egress.",
 "账号组名称": "Account group name",
 "账号组名称已存在，请换一个名称": "That account group name already exists; choose another name",
 "账号组已创建": "Account group created",
 "账号组已删除": "Account group deleted",
 "账号组已更新": "Account group updated",
 "账号组筛选": "Filter accounts by group",
 "账号组管理": "Manage account groups",
 "账号组默认代理模式": "Account group default proxy mode",
 "账号组默认代理组": "Account group default proxy group",
 "账号设置": "Account settings",
 "账号身份": "Account identity",
 "账号邮箱（可选）": "Account email (optional)",
 "账户信息": "Account info",
 "质量": "Quality",
 "购买生图账号": "Buy image-generation accounts",
 "资源占用": "Resource usage",
 "超高": "Extra high",
 "输入 Bearer key": "Enter Bearer key",
 "输入你想生成的画面，也可以粘贴或拖入参考图": "Describe the image you want to generate. You can also paste or drag in reference images",
 "输入希望保留的磁盘剩余空间，系统会从旧图片开始清理。": "Enter the free disk space to keep; the oldest images are removed first.",
 "输入提示词后会在这里显示对话历史。": "Chat history will appear here after you enter a prompt.",
 "输入搜索问题，Enter 搜索，Shift+Enter 换行": "Type a search question. Enter to search, Shift+Enter for a new line",
 "输入文字可以直接对话；切到画图后，在同一个窗口里生成图片、上传参考图和继续编辑。": "Type to chat directly. Switch to image mode to generate images, upload reference images, and keep editing in the same window.",
 "输入消息，Enter 发送，Shift+Enter 换行": "Type a message. Enter to send, Shift+Enter for a new line",
 "运行信息": "Runtime info",
 "运行方式": "Runtime mode",
 "运行环境": "Runtime environment",
 "返回 OpenAI 兼容模型列表。": "Returns an OpenAI-compatible model list.",
 "还没有账号组。先在左侧创建，比如高额度账号、Codex、手动 Token。": "No account groups yet. Create one on the left first, such as high-quota accounts, Codex, or manual tokens.",
 "这条日志没有步骤耗时埋点；新的图片请求会显示分段耗时。": "This log has no step timing data; new image requests will show per-stage timings.",
 "这次尝试没有步骤耗时记录。": "No step timings were recorded for this attempt.",
 "远程 CPA 导入失败": "Remote CPA import failed",
 "连接中断，正在重试": "Connection interrupted, retrying",
 "退出全屏": "Exit fullscreen",
 "退出登录": "Log out",
 "选中账号 · Access Token TXT": "Selected accounts · Access Token TXT",
 "选择 CPA 连接": "Select CPA connection",
 "选择 Sub2API 连接": "Select Sub2API connection",
 "选择代理组": "Select a proxy group",
 "选择备份 JSON 文件": "Choose backup JSON file",
 "选择文件类型": "Select file type",
 "选择模型": "Select a model",
 "选择账号组": "Select an account group",
 "邮箱": "Email",
 "部分完成": "Partially completed",
 "配置图库手动 Push，以及 Studio 生成成功后的自动推送。": "Configure manual Push from the gallery, and automatic push after Studio generation succeeds.",
 "配置尚未加载完成": "Settings have not finished loading",
 "配置已被其他操作更新，当前编辑已保留；刷新版本失败，请手动刷新后重试": "The configuration was updated by another operation. Your current edits were kept, but refreshing the version failed. Refresh manually and try again",
 "配置已被其他操作更新，当前编辑已保留；已刷新版本，请确认后再次保存": "The configuration was updated by another operation. Your current edits were kept and the version was refreshed. Review and save again",
 "重发": "Resend",
 "重命名": "Rename",
 "重命名对话": "Rename chat",
 "重新加载": "Reload",
 "重新生成授权链接": "Regenerate authorization link",
 "重置": "Reset",
 "重试中...": "Retrying...",
 "重试并重新提交": "Retry and resubmit",
 "错误信息已复制": "Error message copied",
 "错误详情": "Error details",
 "间隔": "Interval",
 "阶段": "Stage",
 "阶段时间线": "Stage timeline",
 "限制每个账号同时处理的图片请求数量。默认 1，可设置为 1–3。": "Limits how many image requests each account can process at the same time. Defaults to 1; can be set to 1–3.",
 "限制该节点同时处理的图片请求数；超出后等待同组节点空位，不会改走直连。0 表示不限制。": "Limits how many image requests this node handles at once. Beyond that, requests wait for a free node in the same group and never switch to a direct connection. 0 means unlimited.",
 "限流": "Rate limited",
 "限流/受限": "Rate-limited / restricted",
 "限流账号": "Rate-limited accounts",
 "除文本结果（HTTP 400）外，当前账号未能交付图片时立即尝试其他账号；当前请求不会等待后台账号核验。": "Except for text results (HTTP 400), when the current account fails to deliver an image, another account is tried immediately. The current request does not wait for background account verification.",
 "随页面展开": "Expand with page",
 "隐藏": "Hide",
 "需导出 token": "Token export required",
 "页面加载中": "Loading page",
 "预估": "Estimate",
 "预估完成": "Estimate complete",
 "香港代理池": "Hong Kong proxy pool",
 "高": "High",
 "高额度账号 / Codex / 手动 Token": "High-quota accounts / Codex / Manual tokens",
 "默认": "Default",
 "默认 10 秒，可设置为 5–300 秒。修改后保存在当前浏览器，不写入后端业务配置。": "Defaults to 10 seconds; can be set to 5–300 seconds. Changes are saved in the current browser and are not written to the backend business configuration.",
 "默认 30，0 不限": "Default 30, 0 = unlimited",
 "默认关闭。仅在图片已成功保存后尝试隐藏 ChatGPT 官网 conversation；失败只记录日志，不影响图片返回。关闭时保留官网会话，便于恢复和排查。": "Off by default. Only after the image has been saved successfully does it try to hide the ChatGPT website conversation; failures are only logged and do not affect the image response. When off, the website conversation is kept for recovery and troubleshooting.",
 "默认关闭。仅处理明确请求了尺寸且上游图片小于目标尺寸的结果；自动尺寸和已达到目标尺寸的图片保持原样。": "Off by default. Only applies to results where a size was explicitly requested and the upstream image is smaller than the target size; auto-sized images and images that already reach the target size are left unchanged.",
 "默认出口": "Default egress",
 "默认出口代理组": "Default egress proxy group",
 "默认出口模式": "Default egress mode",
 "默认出口测试失败": "Default egress test failed",
 "默认出口测试结果": "Default egress test result",
 "默认分组": "Default group",
 "默认分组 ID": "Default group ID",
 "默认统计周期": "Default statistics period",
 "（必填）": "(required)",
 "，不写入本地分组绑定": ", without writing local group bindings",
 "，复制完整 JSON，系统会保留其中的 AT、RT 和 ID Token；该接口通常不包含长期 RT。": ", copy the full JSON, and the system keeps its AT, RT, and ID Token. This endpoint usually does not include a long-lived RT."
}

// [Chinese regex source, English replacement]
export const enPatterns: [string, string][] = [
 [
  "^请求失败（HTTP\\ (.*?)）$",
  "Request failed (HTTP $1)"
 ],
 [
  "^提示词库响应中的\\ (.*?)\\ 与列表不一致。$",
  "$1 in the prompt library response does not match the list."
 ],
 [
  "^日志结果图片\\ (.*?)$",
  "Log result image $1"
 ],
 [
  "^选择图片\\ (.*?)$",
  "Select image $1"
 ],
 [
  "^当前展示\\ (.*?)\\ /\\ (.*?)\\ (.*?)$",
  "Showing $1 / $2 $3"
 ],
 [
  "^(.*?)每页数量$",
  "$1 per page"
 ],
 [
  "^(.*?)\\ /\\ 页$",
  "$1 / page"
 ],
 [
  "^(.*?)进度$",
  "$1 progress"
 ],
 [
  "^图片并发\\ (.*?)$",
  "Image concurrency $1"
 ],
 [
  "^，已过滤/去重\\ (.*?)\\ 个$",
  ", $1 filtered/deduplicated"
 ],
 [
  "^当前分组\\ ·\\ (.*?)$",
  "Current group · $1"
 ],
 [
  "^已加载\\ (.*?)\\ 个文件，已选择\\ (.*?)\\ 个$",
  "Loaded $1 ‹1|file|files›, $2 selected"
 ],
 [
  "^已加载\\ (.*?)\\ 个账号，(.*?)\\ 个分组，已选择\\ (.*?)\\ 个$",
  "Loaded $1 ‹1|account|accounts› in $2 ‹2|group|groups›, $3 selected"
 ],
 [
  "^即将从\\ CPA\\ 连接导入\\ (.*?)\\ 个文件里的账号，并写入本地号池。$",
  "About to import accounts from $1 ‹1|file|files› on the CPA connection into the local pool."
 ],
 [
  "^，并按\\ (.*?)\\ 个远端分组创建或复用本地同名分组$",
  ", and create or reuse same-named local groups for $1 remote ‹1|group|groups›"
 ],
 [
  "^即将从\\ Sub2API\\ 连接导入\\ (.*?)\\ 个账号(.*?)。$",
  "About to import $1 ‹1|account|accounts› from the Sub2API connection$2."
 ],
 [
  "^已选择\\ (.*?)\\ 项$",
  "$1 selected"
 ],
 [
  "^移除\\ (.*?)$",
  "Remove $1"
 ],
 [
  "^·\\ (.*?)\\ 张$",
  "· $1 ‹1|image|images›"
 ],
 [
  "^描述你想根据参考图生成的\\ (.*?)$",
  "Describe the $1 you want to generate from the reference images"
 ],
 [
  "^描述你想生成的\\ (.*?)，也可以粘贴或拖入参考图$",
  "Describe the $1 you want to generate. You can also paste or drag in reference images"
 ],
 [
  "^生成\\ (.*?)$",
  "Generate $1"
 ],
 [
  "^(.*?)\\ 条$",
  "$1 ‹1|message|messages›"
 ],
 [
  "^下载\\ (.*?)$",
  "Download $1"
 ],
 [
  "^结果\\ (.*?)$",
  "Result $1"
 ],
 [
  "^1\"\\ class=\"studio\\-result\\-caption\\-label\">结果\\ (.*?)$",
  "1\" class=\"studio-result-caption-label\">Result $1"
 ],
 [
  "^图片\\ (.*?)$",
  "Image $1"
 ],
 [
  "^参考图\\ (.*?)$",
  "Reference image $1"
 ],
 [
  "^(.*?)\\ 文件已删除$",
  "$1 file deleted"
 ],
 [
  "^(.*?)\\ 文件已生成$",
  "$1 file generated"
 ],
 [
  "^(.*?)\\ 生成失败$",
  "$1 generation failed"
 ],
 [
  "^(.*?)\\ 文件$",
  "$1 file"
 ],
 [
  "^显示更早消息（(.*?)\\ 条）$",
  "Show earlier messages ($1)"
 ],
 [
  "^已显示\\ (.*?)\\ /\\ (.*?)\\ 条，库内\\ (.*?)\\ 条$",
  "Showing $1 of $2; $3 in library"
 ],
 [
  "^(.*?)\\ 字$",
  "$1 chars"
 ],
 [
  "^(.*?)\\ 文件任务$",
  "$1 file task"
 ],
 [
  "^0\">耗时\\ (.*?)$",
  "0\">Took $1"
 ],
 [
  "^最近\\ (.*?)\\ 条$",
  "$1 most recent"
 ],
 [
  "^(.*?)\\ 条最近任务$",
  "$1 recent ‹1|task|tasks›"
 ],
 [
  "^(.*?)\\ 秒$",
  "$1 s"
 ],
 [
  "^(.*?)\\ 分\\ (.*?)\\ 秒$",
  "$1 min $2 s"
 ],
 [
  "^(.*?)\\ 分$",
  "$1 min"
 ],
 [
  "^确认删除这条\\ (.*?)\\ 文件任务记录及其本地产物？此操作不可恢复。$",
  "Delete this $1 file task record and its local output? This can't be undone."
 ],
 [
  "^(.*?)\\ 条网页结果$",
  "$1 web ‹1|result|results›"
 ],
 [
  "^来源\\ (.*?)$",
  "Source $1"
 ],
 [
  "^已开始下载\\ (.*?)$",
  "Started downloading $1"
 ],
 [
  "^(.*?)已开始$",
  "$1 started"
 ],
 [
  "^查看版本更新，当前\\ (.*?)$",
  "View version updates, current $1"
 ],
 [
  "^当前主题：(.*?)，点击切换$",
  "Current theme: $1. Click to switch"
 ],
 [
  "^正在加载(.*?)$",
  "Loading $1"
 ],
 [
  "^目标版本\\ (.*?)$",
  "Target version $1"
 ],
 [
  "^检测到新版本\\ (.*?)，当前版本为\\ (.*?)。确认后将下载并安装更新，服务会自动重启，通常需要\\ 30\\ 秒至\\ 2\\ 分钟。$",
  "A new version $1 was found; the current version is $2. After you confirm, the update will be downloaded and installed, and the service will restart automatically. This usually takes 30 seconds to 2 minutes."
 ],
 [
  "^服务器内部错误（HTTP\\ (.*?)），请查看后端日志$",
  "Internal server error (HTTP $1). Check the backend logs."
 ],
 [
  "^目标地址：(.*?)$",
  "Target address: $1"
 ],
 [
  "^选择\\ (.*?)\\ JSON\\ 文件$",
  "Choose $1 JSON file"
 ],
 [
  "^(.*?)占用率$",
  "$1 usage"
 ],
 [
  "^(.*?)天\\ (.*?)小时$",
  "$1d $2h"
 ],
 [
  "^(.*?)小时\\ (.*?)分$",
  "$1h $2m"
 ],
 [
  "^(.*?)分$",
  "$1m"
 ],
 [
  "^(.*?)\\ ·\\ 调用\\ (.*?)\\ ·\\ 成功\\ (.*?)\\ ·\\ 失败\\ (.*?)\\ ·\\ 成功率\\ (.*?)$",
  "$1 · Calls $2 · Success $3 · Failed $4 · Success rate $5"
 ],
 [
  "^删除所选(.*?)$",
  "Delete selected$1"
 ],
 [
  "^下载失败：(.*?)$",
  "Download failed: $1"
 ],
 [
  "^确认删除\\ (.*?)\\ 条日志？$",
  "Delete $1 ‹1|log|logs›?"
 ],
 [
  "^进程内实时窗口，用于观察入口、账号、出口、上游生成、断流和本地拒绝/繁忙；入口排队高时关注\\ CHATGPT2API_THREAD_TOKENS；最近更新：(.*?)$",
  "In-process live window for observing entry, accounts, egress, upstream generation, stream interruptions, and local rejections/busy states. When entry queueing is high, check CHATGPT2API_THREAD_TOKENS. Last updated: $1"
 ],
 [
  "^当前并发\\ (.*?)\\ /\\ (.*?)$",
  "Concurrent $1 / $2"
 ],
 [
  "^入口排队\\ (.*?)$",
  "Entry queue $1"
 ],
 [
  "^处理中\\ (.*?)$",
  "Processing $1"
 ],
 [
  "^(.*?)\\ 条消息$",
  "$1 ‹1|message|messages›"
 ],
 [
  "^确定删除“(.*?)”吗？本地历史会被移除。$",
  "Delete \"$1\"? The local history will be removed."
 ],
 [
  "^确定清空“(.*?)”中的消息吗？$",
  "Clear the messages in \"$1\"?"
 ],
 [
  "^读取图片失败：HTTP\\ (.*?)$",
  "Failed to read image: HTTP $1"
 ],
 [
  "^局部修改要求：(.*?)$",
  "Local edit request: $1"
 ],
 [
  "^局部修改：(.*?)$",
  "Local edit: $1"
 ],
 [
  "^选择账号\\ (.*?)$",
  "Select account $1"
 ],
 [
  "^图片额度：(.*?)\\ →\\ (.*?)$",
  "Image quota: $1 → $2"
 ],
 [
  "^绑定到\\ (.*?)$",
  "Bind to $1"
 ],
 [
  "^取消选择\\ \\((.*?)\\)$",
  "Clear selection ($1)"
 ],
 [
  "^即将(.*?)当前筛选条件下选中的\\ (.*?)\\ 个账号，是否继续？$",
  "This will $1 the $2 account‹2||s› selected under the current filters. Continue?"
 ],
 [
  "^即将(.*?)\\ (.*?)\\ 个账号，后端会按账号批量任务并发执行。是否继续？$",
  "This will $1 $2 account‹2||s›; the backend runs them concurrently as a bulk account task. Continue?"
 ],
 [
  "^开始(.*?)$",
  "Start $1"
 ],
 [
  "^(.*?)失败$",
  "$1 failed"
 ],
 [
  "^确认删除账号\\ (.*?)\\ 吗？此操作不可恢复。$",
  "Delete account $1? This cannot be undone."
 ],
 [
  "^确认对选中的\\ (.*?)\\ 个账号执行该操作吗？$",
  "Run this action on the $1 selected account‹1||s›?"
 ],
 [
  "^确认把选中的\\ (.*?)\\ 个账号绑定到\\ (.*?)\\ 吗？$",
  "Bind the $1 selected account‹1||s› to $2?"
 ],
 [
  "^账号\\ (.*?)\\ (.*?)失败：(.*?)$",
  "Account $1 $2 failed: $3"
 ],
 [
  "^账号\\ (.*?)\\ 已更新$",
  "Account $1 updated"
 ],
 [
  "^确认(.*?)$",
  "Confirm $1"
 ],
 [
  "^即将对账号\\ (.*?)\\ 执行“(.*?)”。这会影响该账号是否参与后续请求分配，是否继续？$",
  "You are about to run \"$2\" on account $1. This affects whether the account takes part in future request allocation. Continue?"
 ],
 [
  "^即将同步账号\\ (.*?)\\ 的远端信息和额度，是否继续？$",
  "This will sync the remote info and quota of account $1. Continue?"
 ],
 [
  "^即将使用账号\\ (.*?)\\ 的\\ RT\\ 刷新\\ AT，是否继续？$",
  "This will use the RT of account $1 to refresh its AT. Continue?"
 ],
 [
  "^导出(.*?)账号$",
  "Export $1 accounts"
 ],
 [
  "^导出\\ (.*?)$",
  "Export $1"
 ],
 [
  "^，跳过\\ (.*?)\\ 个$",
  ", $1 skipped"
 ],
 [
  "^已导出\\ (.*?)\\ 个账号(.*?)\\ ·\\ (.*?)$",
  "Exported $1 account‹1||s›$2 · $3"
 ],
 [
  "^未知代理组\\ ·\\ (.*?)$",
  "Unknown proxy group · $1"
 ],
 [
  "^代理组：(.*?)$",
  "Proxy group: $1"
 ],
 [
  "^(.*?)\\ 是空文件$",
  "$1 is an empty file"
 ],
 [
  "^(.*?)\\ 中没有找到\\ access_token$",
  "No access_token found in $1"
 ],
 [
  "^本次导入同步失败\\ (.*?)\\ 个。\\\\n后端确认其中\\ (.*?)\\ 个账号鉴权已经失效，是否直接删除？\\\\n\\\\n只会删除本次导入且已确认失效的账号；正常、限流、暂时检测失败和历史账号都会保留。$",
  "$1 account‹1||s› failed to sync in this import.\\nThe backend confirmed that authentication is no longer valid for $2 of them. Delete them now?\\n\\nOnly accounts from this import that are confirmed invalid will be deleted; normal, rate-limited, temporarily unchecked, and older accounts are all kept."
 ],
 [
  "^删除\\ (.*?)\\ 个$",
  "Delete $1"
 ],
 [
  "^即将导入\\ (.*?)\\ 个账号。(.*?)是否继续？$",
  "This will import $1 account‹1||s›. $2 Continue?"
 ],
 [
  "^账号已保存，后续同步未完成：(.*?)$",
  "Accounts saved, but the follow-up sync did not finish: $1"
 ],
 [
  "^(.*?)已保存，但同步失败$",
  "$1: saved, but sync failed"
 ],
 [
  "^凭据已保存，后续同步未完成：(.*?)$",
  "Credentials saved, but the follow-up sync did not finish: $1"
 ],
 [
  "^即将读取\\ (.*?)\\ 个备份文件并恢复其中的账号凭据、配置与状态。是否继续？$",
  "This will read $1 backup file‹1||s› and restore the account credentials, settings, and status in ‹1|it|them›. Continue?"
 ],
 [
  "^即将读取\\ (.*?)\\ 个\\ (.*?)\\ JSON\\ 文件，保存账号后同步账号与额度。是否继续？$",
  "This will read $1 $2 JSON file‹1||s›, save the accounts, then sync accounts and quota. Continue?"
 ],
 [
  "^代理可用：(.*?)\\ ms，HTTP\\ (.*?)$",
  "Proxy is available: $1 ms, HTTP $2"
 ],
 [
  "^代理不可用：(.*?)$",
  "Proxy is unavailable: $1"
 ],
 [
  "^当前账号没有可复制的\\ (.*?)$",
  "This account has no $1 to copy"
 ],
 [
  "^(.*?)\\ 已复制$",
  "$1 copied"
 ],
 [
  "^复制\\ (.*?)\\ 失败$",
  "Failed to copy $1"
 ],
 [
  "^账号组：(.*?)$",
  "Account group: $1"
 ],
 [
  "^代理：(.*?)$",
  "Proxy: $1"
 ],
 [
  "^将从旧图片开始清理，直到磁盘剩余空间尽量达到\\ (.*?)。此操作不可恢复，确定继续吗？$",
  "Images will be removed starting with the oldest until free disk space reaches $1 where possible. This cannot be undone. Continue?"
 ],
 [
  "^确定要删除\\ (.*?)\\ 吗？此操作不可恢复。$",
  "Delete $1? This cannot be undone."
 ],
 [
  "^确定要删除已选择的\\ (.*?)\\ 张图片吗？此操作不可恢复。$",
  "Delete the $1 selected images? This cannot be undone."
 ],
 [
  "^已选择\\ (.*?)\\ 张$",
  "$1 selected"
 ],
 [
  "^已删除\\ (.*?)\\ 张图片$",
  "Deleted $1 ‹1|image|images›"
 ],
 [
  "^已打包\\ (.*?)\\ 张图片$",
  "Packed $1 ‹1|image|images›"
 ],
 [
  "^第\\ (.*?)\\ /\\ (.*?)\\ 页，共\\ (.*?)\\ 张$",
  "Page $1 / $2, $3 ‹3|image|images› total"
 ],
 [
  "^(.*?)\\ 个$",
  "$1 files"
 ],
 [
  "^(.*?)\\ 个\\ /\\ (.*?)$",
  "$1 files / $2"
 ],
 [
  "^尝试\\ (.*?)$",
  "Attempt $1"
 ],
 [
  "^选择日志\\ (.*?)$",
  "Select log $1"
 ],
 [
  "^实际分辨率：(.*?)$",
  "Actual resolution: $1"
 ],
 [
  "^已选择\\ (.*?)\\ 条$",
  "$1 selected"
 ],
 [
  "^已删除\\ (.*?)\\ 条日志$",
  "Deleted $1 ‹1|log|logs›"
 ],
 [
  "^上一账号：(.*?)$",
  "Previous account: $1"
 ],
 [
  "^ID：(.*?)$",
  "ID: $1"
 ],
 [
  "^点击复制\\ (.*?)$",
  "Click to copy $1"
 ],
 [
  "^默认出口可用，耗时\\ (.*?)ms$",
  "Default egress is available ($1ms)"
 ],
 [
  "^出口\\ (.*?)$",
  "Egress $1"
 ],
 [
  "^即将(.*?)代理组\\ (.*?)。绑定到该组的账号组会受到影响，是否继续？$",
  "You are about to $1 proxy group $2. Account groups bound to this group will be affected. Continue?"
 ],
 [
  "^代理组\\ (.*?)\\ 已(.*?)$",
  "Proxy group $1 $2"
 ],
 [
  "^确认删除代理组\\ (.*?)？该代理组当前未被任何出口、账号组或账号引用，删除后无法恢复。$",
  "Delete proxy group $1? It is not currently referenced by any egress, account group, or account. This cannot be undone."
 ],
 [
  "^(.*?)：请先填写代理地址$",
  "$1: enter a proxy address first"
 ],
 [
  "^即将使用代理组\\ (.*?)\\ 的节点\\ (.*?)\\ 发起外部网络测试请求。请确认当前允许测试该代理连接。$",
  "This will send an external network test request through node $2 of proxy group $1. Confirm that testing this proxy connection is allowed."
 ],
 [
  "^节点检测通过，耗时\\ (.*?)ms$",
  "Node check passed in $1ms"
 ],
 [
  "^即将测试代理组\\ (.*?)\\ 内的\\ (.*?)\\ 个节点。每个节点都会发起外部网络测试请求，是否继续？$",
  "This will test the $2 ‹2|node|nodes› in proxy group $1. Each node sends an external network test request. Continue?"
 ],
 [
  "^正在检测\\ (.*?)\\ 个节点\\.\\.\\.$",
  "Checking $1 ‹1|node|nodes›..."
 ],
 [
  "^已添加\\ (.*?)\\ 个$",
  "$1 added"
 ],
 [
  "^跳过重复\\ (.*?)\\ 个$",
  "$1 duplicate‹1||s› skipped"
 ],
 [
  "^(.*?)\\ 行格式错误$",
  "$1 ‹1|line has|lines have› invalid format"
 ],
 [
  "^(.*?)\\ 行$",
  "$1 ‹1|line|lines›"
 ],
 [
  "^(.*?)；保存代理组后生效$",
  "$1; takes effect after you save the proxy group"
 ],
 [
  "^不可删除\\ ·\\ (.*?)$",
  "Cannot delete · $1"
 ],
 [
  "^·\\ 分组\\ (.*?)$",
  "· Group $1"
 ],
 [
  "^创建\\ (.*?)\\ ·\\ 最近使用\\ (.*?)$",
  "Created $1 · Last used $2"
 ],
 [
  "^备份已完成：(.*?)$",
  "Backup complete: $1"
 ],
 [
  "^确定删除备份\\ (.*?)？$",
  "Delete backup $1?"
 ],
 [
  "^按当前保留策略检测到\\ (.*?)\\ 项可清理数据，预计释放\\ (.*?)。$",
  "Under the current retention policy, $1 items can be cleaned up, freeing about $2."
 ],
 [
  "^日志：(.*?)\\ 条，保留\\ (.*?)\\ 小时。$",
  "Logs: $1 entries, retained for $2 hours."
 ],
 [
  "^图片：(.*?)\\ 个，保留\\ (.*?)\\ 小时。$",
  "Images: $1 files, retained for $2 hours."
 ],
 [
  "^清理完成：删除\\ (.*?)\\ 项，释放\\ (.*?)$",
  "Cleanup complete: deleted $1 items, freed $2"
 ],
 [
  "^按当前账号策略检测到\\ (.*?)\\ 个可移除账号。$",
  "Under the current account policy, $1 accounts can be removed."
 ],
 [
  "^确认鉴权失效账号：(.*?)\\ 个。$",
  "Accounts with confirmed invalid authentication: $1."
 ],
 [
  "^额度耗尽账号：(.*?)\\ 个。$",
  "Accounts with exhausted quota: $1."
 ],
 [
  "^账号清理完成：移除\\ (.*?)\\ 个账号$",
  "Account cleanup complete: removed $1 accounts"
 ],
 [
  "^请先保存设置，再(.*?)$",
  "Save your settings before you $1"
 ],
 [
  "^清理检测失败：(.*?)$",
  "Cleanup check failed: $1"
 ],
 [
  "^清理失败：(.*?)$",
  "Cleanup failed: $1"
 ],
 [
  "^账号清理检测失败：(.*?)$",
  "Account cleanup check failed: $1"
 ],
 [
  "^账号清理失败：(.*?)$",
  "Account cleanup failed: $1"
 ],
 [
  "^确定删除\\ (.*?)？账号页将不能再从这个\\ CPA\\ 连接导入。$",
  "Delete $1? The Accounts page will no longer be able to import from this CPA connection."
 ],
 [
  "^即将访问\\ CPA\\ 连接\\ (.*?)\\ 并读取远程文件列表。请确认当前允许连接该外部服务。$",
  "This will contact the CPA connection $1 and read the remote file list. Confirm that connecting to this external service is allowed."
 ],
 [
  "^CPA\\ 连接可用，读取到\\ (.*?)\\ 个文件$",
  "CPA connection is working; read $1 files"
 ],
 [
  "^确定删除\\ (.*?)？账号页将不能再从这个\\ Sub2API\\ 连接导入。$",
  "Delete $1? The Accounts page will no longer be able to import from this Sub2API connection."
 ],
 [
  "^即将访问\\ Sub2API\\ 连接\\ (.*?)\\ 并读取远程分组列表。请确认当前允许连接该外部服务。$",
  "This will contact the Sub2API connection $1 and read the remote group list. Confirm that connecting to this external service is allowed."
 ],
 [
  "^Sub2API\\ 连接可用，读取到\\ (.*?)\\ 个分组$",
  "Sub2API connection is working; read $1 groups"
 ],
 [
  "^上传\\ (.*?)，跳过\\ (.*?)，失败\\ (.*?)$",
  "Uploaded $1, skipped $2, failed $3"
 ],
 [
  "^(.*?)\\ 个词源$",
  "$1 ‹1|source|sources›"
 ],
 [
  "^确定删除用户密钥「(.*?)」吗？删除后这条密钥将无法继续调用接口。$",
  "Delete the user key \"$1\"? Once deleted, this key can no longer call the API."
 ],
 [
  "^curl\\ (.*?)/chat/completions\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"model\":\"gpt\\-5\\-mini\",\"messages\":\\[\\{\"role\":\"user\",\"content\":\"你好\"\\}\\]\\}'$",
  "curl $1/chat/completions \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"model\":\"gpt-5-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
 ],
 [
  "^curl\\ (.*?)/responses\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"model\":\"gpt\\-5\\-mini\",\"input\":\"生成一张未来城市图片\"\\}'$",
  "curl $1/responses \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"model\":\"gpt-5-mini\",\"input\":\"Generate an image of a futuristic city\"}'"
 ],
 [
  "^curl\\ (.*?)/messages\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"model\":\"gpt\\-5\\-mini\",\"max_tokens\":1024,\"messages\":\\[\\{\"role\":\"user\",\"content\":\"你好\"\\}\\]\\}'$",
  "curl $1/messages \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"model\":\"gpt-5-mini\",\"max_tokens\":1024,\"messages\":[{\"role\":\"user\",\"content\":\"Hello\"}]}'"
 ],
 [
  "^curl\\ (.*?)/search\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"prompt\":\"今天的\\ OpenAI\\ 新闻\"\\}'$",
  "curl $1/search \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"prompt\":\"Today's OpenAI news\"}'"
 ],
 [
  "^curl\\ (.*?)/images/generations\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"model\":\"gpt\\-image\\-2\",\"prompt\":\"一张极简产品海报\",\"n\":1\\}'$",
  "curl $1/images/generations \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"model\":\"gpt-image-2\",\"prompt\":\"A minimalist product poster\",\"n\":1}'"
 ],
 [
  "^curl\\ (.*?)/images/edits\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-F\\ \"model=gpt\\-image\\-2\"\\ \\\\\\\\\\\\n\\ \\ \\-F\\ \"prompt=改成赛博朋克夜景\"\\ \\\\\\\\\\\\n\\ \\ \\-F\\ \"image=@\\./input\\.png\"$",
  "curl $1/images/edits \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -F \"model=gpt-image-2\" \\\\\\n  -F \"prompt=Change it to a cyberpunk night scene\" \\\\\\n  -F \"image=@./input.png\""
 ],
 [
  "^curl\\ (.*?)/editable\\-file\\-tasks\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"kind\":\"ppt\",\"prompt\":\"做一份产品发布会\\ PPT\"\\}'$",
  "curl $1/editable-file-tasks \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"kind\":\"ppt\",\"prompt\":\"Create a product launch PPT\"}'"
 ],
 [
  "^curl\\ (.*?)/ppt/generations\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"prompt\":\"生成一份市场分析\\ PPT\"\\}'$",
  "curl $1/ppt/generations \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"prompt\":\"Generate a market analysis PPT\"}'"
 ],
 [
  "^curl\\ (.*?)/psd/generations\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Content\\-Type:\\ application/json\"\\ \\\\\\\\\\\\n\\ \\ \\-H\\ \"Authorization:\\ Bearer\\ (.*?)\"\\ \\\\\\\\\\\\n\\ \\ \\-d\\ '\\{\"prompt\":\"生成一张电商海报\\ PSD\"\\}'$",
  "curl $1/psd/generations \\\\\\n  -H \"Content-Type: application/json\" \\\\\\n  -H \"Authorization: Bearer $2\" \\\\\\n  -d '{\"prompt\":\"Generate an e-commerce poster PSD\"}'"
 ],
 [
  "^不能小于\\ (.*?)$",
  "Must not be less than $1"
 ],
 [
  "^不能大于\\ (.*?)$",
  "Must not be greater than $1"
 ],
 [
  "^画图请求：(.*?)$",
  "Image request: $1"
 ],
 [
  "^搜索请求：(.*?)$",
  "Search request: $1"
 ],
 [
  "^(.*?)\\ 文件请求：(.*?)$",
  "$1 file request: $2"
 ],
 [
  "^(.*?)\\ 文件任务已提交$",
  "$1 file task submitted"
 ],
 [
  "^(\\d[\\d,.]*) 张$",
  "$1 ‹1|image|images›"
 ],
 [
  "^(\\d[\\d,.]*) 条$",
  "$1 ‹1|entry|entries›"
 ],
 [
  "^(\\d[\\d,.]*) 条 · (.*)$",
  "$1 ‹1|message|messages› · $2"
 ],
 [
  "^(\\d[\\d,.]*) 次尝试$",
  "$1 ‹1|attempt|attempts›"
 ],
 [
  "^切换 (\\d[\\d,.]*) 次$",
  "$1 ‹1|switch|switches›"
 ],
 [
  "^(\\d[\\d,.]*) 步$",
  "$1 ‹1|step|steps›"
 ],
 [
  "^(\\d[\\d,.]*) 个阶段$",
  "$1 ‹1|stage|stages›"
 ],
 [
  "^(\\d[\\d,.]*) 个连接$",
  "$1 ‹1|connection|connections›"
 ],
 [
  "^(\\d[\\d,.]*) 个节点$",
  "$1 ‹1|node|nodes›"
 ],
 [
  "^(\\d[\\d,.]*) 核$",
  "$1 ‹1|core|cores›"
 ],
 [
  "^(\\d[\\d,.]*) 个账号 · 默认出口：(.*)$",
  "$1 ‹1|account|accounts› · Default egress: $2"
 ],
 [
  "^多出口 · (\\d[\\d,.]*) 个节点$",
  "Multi-egress · $1 ‹1|node|nodes›"
 ],
 [
  "^请修正以下 (\\d[\\d,.]*) 行$",
  "Fix the following $1 ‹1|line|lines›"
 ],
 [
  "^(\\d[\\d,.]*) 张 · 成功 (.*?) · 失败 (.*)$",
  "$1 ‹1|image|images› · Success $2 · Failed $3"
 ],
 [
  "^将在 (.*?) 后自动删除$",
  "Will be deleted automatically in $1"
 ],
 [
  "^(\\d[\\d,.]*) 条提示词，(\\d[\\d,.]*) 个启用词源$",
  "$1 ‹1|prompt|prompts›, $2 enabled ‹2|source|sources›"
 ],
 [
  "^停用 · (.*)$",
  "Disabled · $1"
 ],
 [
  "^(.*?) · (\\d[\\d,.]*) 个节点$",
  "$1 · $2 ‹2|node|nodes›"
 ],
 [
  "^确认删除账号组「(.*?)」吗？当前 (\\d[\\d,.]*) 个账号会变为未分组。$",
  "Delete the account group \"$1\"? $2 account‹2||s› will become ungrouped."
 ],
 [
  "^确认删除账号组「(.*?)」吗？不会删除任何账号。$",
  "Delete the account group \"$1\"? No accounts will be deleted."
 ],
 [
  "^即将把全部 (\\d[\\d,.]*) 个账号导出为可再次导入的完整 JSON。文件包含账号凭据和配置，请只在可信环境保存。$",
  "You are about to export all $1 account‹1||s› as full JSON that can be imported again. The file contains account credentials and settings, so only save it in a trusted environment."
 ],
 [
  "^即将把选中 (\\d[\\d,.]*) 个账号导出为可再次导入的完整 JSON。文件包含账号凭据和配置，请只在可信环境保存。$",
  "You are about to export the selected $1 account‹1||s› as full JSON that can be imported again. The file contains account credentials and settings, so only save it in a trusted environment."
 ],
 [
  "^即将把全部 (\\d[\\d,.]*) 个账号导出为 TXT，每行一个 Access Token，不包含 RT、ID Token 和账号配置。$",
  "You are about to export all $1 account‹1||s› as TXT, one Access Token per line, without RT, ID Token, or account settings."
 ],
 [
  "^即将把选中 (\\d[\\d,.]*) 个账号导出为 TXT，每行一个 Access Token，不包含 RT、ID Token 和账号配置。$",
  "You are about to export the selected $1 account‹1||s› as TXT, one Access Token per line, without RT, ID Token, or account settings."
 ],
 [
  "^选中账号 · 完整 JSON( \\((.*?)\\))?$",
  "Selected accounts · Full JSON$1"
 ],
 [
  "^已显示 (.*?) / (.*?) 条，库内 (.*?) 条$",
  "Showing $1 / $2, $3 in library"
 ]
]
