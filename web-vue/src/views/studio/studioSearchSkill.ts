export type SearchSkillLanguage = 'zh' | 'en'

export type SearchSkillPromptInput = {
  baseUrl: string
  language: SearchSkillLanguage
}

export type SearchSkillRuntimeInput = {
  language: SearchSkillLanguage
  getBaseUrl: () => string
  loadRuntimeConfig: () => Promise<unknown>
}

function cleanBaseUrl(value: string) {
  return String(value || '').trim().replace(/\/+$/, '')
}

export function searchSkillEndpoint(baseUrl: string) {
  return `${cleanBaseUrl(baseUrl)}/v1/search`
}

export function buildSearchSkillDocument(input: SearchSkillPromptInput) {
  const endpoint = searchSkillEndpoint(input.baseUrl)

  if (input.language === 'en') {
    return `---
name: chatgpt2api-search
description: Use when current web search is needed through this chatgpt2api server. Call the configured HTTP search endpoint with a prompt and return the answer with source URLs.
---

# ChatGPT2API Search

Use this skill when the user asks for current web search, online lookup, recent information, or source-backed answers.

## Request

POST ${endpoint}

Headers:

Authorization: Bearer \${CHATGPT2API_API_KEY}
Content-Type: application/json

JSON body:

{
  "prompt": "<search question>"
}

## Response handling

- Use \`answer\` as the main response.
- Include source URLs from \`sources\` when available.
- If the endpoint returns an error, summarize the error and ask whether to retry.

## Authentication

- Read the API key from the \`CHATGPT2API_API_KEY\` environment variable at request time.
- Never write the real API key into this skill file, prompts, logs, or source control.
- If the environment variable is missing, stop and ask the user to configure it before sending a request.

Set it before starting the client that runs this skill (replace \`<your-api-key>\`):

- PowerShell: \`$env:CHATGPT2API_API_KEY = '<your-api-key>'\`
- Bash / zsh: \`export CHATGPT2API_API_KEY='<your-api-key>'\``
  }

  return `---
name: chatgpt2api-search
description: 当用户需要联网搜索、查询最新信息、核实事实或需要来源链接时，调用本地 chatgpt2api 搜索接口。
---

# ChatGPT2API 搜索

当用户要求联网搜索、查询最新信息、核实资料、查新闻、查价格、查文档更新或需要来源链接时，使用这个 skill。

## 接口

POST ${endpoint}

Headers:

Authorization: Bearer \${CHATGPT2API_API_KEY}
Content-Type: application/json

Body:

{
  "prompt": "<用户要搜索的问题>"
}

## 返回处理

- 使用接口返回的 \`answer\` 作为主要回答。
- 如果有 \`sources\`，在回答里附上来源链接。
- 如果接口报错，简要说明错误并询问是否重试。

## 鉴权

- 发起请求时从 \`CHATGPT2API_API_KEY\` 环境变量读取 API Key。
- 不要把真实 API Key 写入本 Skill、提示词、日志或版本控制。
- 如果环境变量未设置，停止请求并提示用户先完成配置。

启动运行此 Skill 的客户端之前先设置环境变量（将 \`<your-api-key>\` 替换为实际密钥）：

- PowerShell：\`$env:CHATGPT2API_API_KEY = '<your-api-key>'\`
- Bash / zsh：\`export CHATGPT2API_API_KEY='<your-api-key>'\``
}

export function buildSearchSkillInstallPrompt(input: SearchSkillPromptInput) {
  const document = buildSearchSkillDocument(input)

  if (input.language === 'en') {
    return `Please install a local web-search skill on this machine.

Requirements:
1. Install this as a local skill according to the current environment's skill rules.
2. Skill name: chatgpt2api-search
3. File name: SKILL.md
4. Only create or update this skill file.
5. Do not write a real API key into the skill. It must read \`CHATGPT2API_API_KEY\` from the environment at runtime.

SKILL.md content:

\`\`\`markdown
${document}
\`\`\``
  }

  return `请帮我在本机安装一个用于联网搜索的 skill。

要求：
1. 按当前环境的 skill 安装规范，把它安装成本地 skill。
2. skill 名称为：chatgpt2api-search
3. 文件名为：SKILL.md
4. 只创建或更新这个 skill 文件，不要修改其他无关文件。
5. 不要把真实 API Key 写入 skill，运行时必须从环境变量 \`CHATGPT2API_API_KEY\` 读取。

SKILL.md 内容：

\`\`\`markdown
${document}
\`\`\``
}

export async function loadSearchSkillInstallPrompt(input: SearchSkillRuntimeInput) {
  await input.loadRuntimeConfig()
  return buildSearchSkillInstallPrompt({
    baseUrl: input.getBaseUrl(),
    language: input.language,
  })
}
