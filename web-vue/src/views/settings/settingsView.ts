import type { BackupState } from '@/api/settings'
import type { Settings, SettingsFieldMetadata } from '@/types/api'

export type SettingsSelectOption = {
  label: string
  value: string
}

export type SettingsApiDocItem = {
  title: string
  method: string
  path: string
  description: string
  example: string
}

export type NumberSettingOptions = {
  integer?: boolean
  metadata?: () => SettingsFieldMetadata | null | undefined
  enabled?: () => boolean
}

export type SettingsFields = Record<string, SettingsFieldMetadata>

const dateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
})

export const settingsTabs: SettingsSelectOption[] = [
  { value: 'basic', label: '基础配置' },
  { value: 'storage', label: '图片存储与审核' },
  { value: 'prompts', label: '提示词源' },
  { value: 'backup', label: 'R2 备份' },
  { value: 'keys', label: '用户密钥' },
  { value: 'api-docs', label: '接口接入' },
  { value: 'canvas', label: '画布入口' },
  { value: 'cpa', label: 'CPA' },
  { value: 'sub2api', label: 'Sub2API' },
]

const settingsOptionLabels: Record<string, Record<string, string>> = {
  image_upscale_engine: {
    sharp_lanczos3: 'Sharp / Lanczos3',
    pillow_lanczos: 'Pillow / Lanczos',
  },
  'image_storage.mode': {
    local: '仅本地',
    webdav: '仅 WebDAV',
    both: '本地 + WebDAV',
  },
  'backup.include': {
    image_tasks: '图片任务记录',
    editable_files: 'PPT / PSD 文件',
    images: '图片文件目录',
  },
}

export function settingsField(
  fields: SettingsFields | null | undefined,
  path: string,
): SettingsFieldMetadata | null {
  return fields?.[path] || null
}

export function settingsFieldReadOnly(
  fields: SettingsFields | null | undefined,
  path: string,
): boolean {
  return Boolean(settingsField(fields, path)?.read_only)
}

export function settingsFieldOptions(
  fields: SettingsFields | null | undefined,
  path: string,
  currentValue?: unknown,
): SettingsSelectOption[] {
  const values = [...(settingsField(fields, path)?.options || [])]
  const currentValues = Array.isArray(currentValue) ? currentValue : [currentValue]
  for (const currentValueItem of currentValues) {
    const current = String(currentValueItem ?? '').trim()
    if (current && !values.includes(current)) values.unshift(current)
  }
  const labels = settingsOptionLabels[path] || {}
  return Array.from(new Set(values)).map((value) => ({
    value,
    label: labels[value] || value,
  }))
}

export function settingsBooleanFieldOptions(
  fields: SettingsFields | null | undefined,
  prefix: string,
  currentValues: Record<string, boolean>,
): SettingsSelectOption[] {
  const values = Object.keys(fields || {})
    .filter((path) => path.startsWith(prefix))
    .map((path) => path.slice(prefix.length))
  for (const value of Object.keys(currentValues)) {
    if (!values.includes(value)) values.push(value)
  }
  const labelGroup = prefix.replace(/\.$/, '')
  const labels = settingsOptionLabels[labelGroup] || {}
  return values.map((value) => ({ value, label: labels[value] || value }))
}

export function backupStatusText(state: BackupState | null | undefined) {
  if (!state) return '未加载'
  if (state.running) return '备份中'
  if (state.last_status === 'success') return '最近成功'
  if (state.last_status === 'error') return '最近失败'
  return state.last_status || '未执行'
}

export function formatBytes(value: unknown) {
  const bytes = Number(value) || 0
  if (bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let size = bytes
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`
}

export function formatDateTime(value: unknown) {
  const raw = String(value || '').trim()
  if (!raw) return '-'
  const parsed = new Date(raw)
  if (Number.isNaN(parsed.getTime())) return raw
  return dateTimeFormatter.format(parsed)
}

export function settingsFingerprint(value: Settings | null | undefined): string {
  return value ? JSON.stringify(value) : ''
}

export function buildApiDocItems(serviceBaseUrl: string, currentApiKey: string): SettingsApiDocItem[] {
  const cleanServiceBaseUrl = String(serviceBaseUrl || '').replace(/\/$/, '')
  const openAIBaseUrl = `${cleanServiceBaseUrl}/v1`
  return [
    {
      title: '模型列表',
      method: 'GET',
      path: '/v1/models',
      description: '返回 OpenAI 兼容模型列表。',
      example: `curl ${openAIBaseUrl}/models \\\n  -H "Authorization: Bearer ${currentApiKey}"`,
    },
    {
      title: '聊天补全',
      method: 'POST',
      path: '/v1/chat/completions',
      description: 'OpenAI 兼容聊天补全接口，图片兼容场景也会解析 n 等参数。',
      example: `curl ${openAIBaseUrl}/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"你好"}]}'`,
    },
    {
      title: 'Responses',
      method: 'POST',
      path: '/v1/responses',
      description: '兼容 Responses 输入结构，支持文本与工具调用场景。',
      example: `curl ${openAIBaseUrl}/responses \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"model":"gpt-5-mini","input":"生成一张未来城市图片"}'`,
    },
    {
      title: 'Messages',
      method: 'POST',
      path: '/v1/messages',
      description: 'Anthropic Messages 兼容入口，支持 Authorization Bearer 或 x-api-key 鉴权。',
      example: `curl ${openAIBaseUrl}/messages \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"model":"gpt-5-mini","max_tokens":1024,"messages":[{"role":"user","content":"你好"}]}'`,
    },
    {
      title: '联网搜索',
      method: 'POST',
      path: '/v1/search',
      description: '本地搜索兼容入口，返回 answer 与 sources。',
      example: `curl ${openAIBaseUrl}/search \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"prompt":"今天的 OpenAI 新闻"}'`,
    },
    {
      title: '图片生成',
      method: 'POST',
      path: '/v1/images/generations',
      description: '图片生成接口，支持 prompt、model、n、size、quality 等参数。',
      example: `curl ${openAIBaseUrl}/images/generations \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"model":"gpt-image-2","prompt":"一张极简产品海报","n":1}'`,
    },
    {
      title: '图片编辑',
      method: 'POST',
      path: '/v1/images/edits',
      description: '图片编辑接口，支持 multipart 上传参考图。',
      example: `curl ${openAIBaseUrl}/images/edits \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -F "model=gpt-image-2" \\\n  -F "prompt=改成赛博朋克夜景" \\\n  -F "image=@./input.png"`,
    },
    {
      title: '创建可编辑文件任务',
      method: 'POST',
      path: '/v1/editable-file-tasks',
      description: '统一创建 PPT/PSD 文件任务，kind 可填 ppt 或 psd。',
      example: `curl ${openAIBaseUrl}/editable-file-tasks \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"kind":"ppt","prompt":"做一份产品发布会 PPT"}'`,
    },
    {
      title: '查询可编辑文件任务',
      method: 'GET',
      path: '/v1/editable-file-tasks?ids={taskId1,taskId2}',
      description: '按任务 ID 查询 PPT/PSD 文件生成状态。',
      example: `curl "${openAIBaseUrl}/editable-file-tasks?ids=task_1,task_2" \\\n  -H "Authorization: Bearer ${currentApiKey}"`,
    },
    {
      title: 'PPT 生成任务',
      method: 'POST',
      path: '/v1/ppt/generations',
      description: '直接创建 PPT 生成任务，返回任务 ID 后再查询状态。',
      example: `curl ${openAIBaseUrl}/ppt/generations \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"prompt":"生成一份市场分析 PPT"}'`,
    },
    {
      title: 'PSD 生成任务',
      method: 'POST',
      path: '/v1/psd/generations',
      description: '直接创建 PSD 生成任务，返回任务 ID 后再查询状态。',
      example: `curl ${openAIBaseUrl}/psd/generations \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${currentApiKey}" \\\n  -d '{"prompt":"生成一张电商海报 PSD"}'`,
    },
    {
      title: '文件下载',
      method: 'GET',
      path: '/files/{file_path}',
      description: '公开下载 PPT/PSD 任务生成的文件或压缩包，无需鉴权。',
      example: `curl ${cleanServiceBaseUrl}/files/{file_path}`,
    },
  ]
}
