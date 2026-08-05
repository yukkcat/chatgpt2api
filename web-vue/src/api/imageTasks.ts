import apiClient from './client'

export type ImageTaskStatus = 'queued' | 'running' | 'success' | 'partial_success' | 'failed' | 'text_review'
export type ImageTaskMode = 'generate' | 'edit'

export interface ImageTaskAsset {
  url: string
  path: string
  b64_json: string
  revised_prompt: string
  width: number | null
  height: number | null
}

export interface ImageTaskActions {
  resume_poll: boolean
}

export interface ImageTask {
  id: string
  status: ImageTaskStatus
  terminal: boolean
  mode: ImageTaskMode
  model: string
  size: string
  quality: string
  stage_code: string
  stage_label: string
  created_at: string
  updated_at: string
  requested_count: number
  succeeded_count: number
  failed_count: number
  pending_count: number
  duration_ms: number | null
  elapsed_ms: number | null
  error_code: string
  public_error: string
  results: ImageTaskAsset[]
  actions: ImageTaskActions
}

export interface ImageTasksResponse {
  items: ImageTask[]
  missing_ids: string[]
}

export interface CreateGenerationTaskInput {
  prompt: string
  model?: string
  n?: number
  size?: string
  quality?: string
  clientTaskId?: string
}

export interface CreateEditTaskInput extends CreateGenerationTaskInput {
  files?: File[]
  imageUrls?: string[]
  mask?: File
}

export const DEFAULT_IMAGE_MODEL = 'gpt-image-2'
export const DEFAULT_IMAGE_QUALITY = 'auto'
export const DEFAULT_IMAGE_SIZE = 'auto'

export interface ImageSizeOption {
  label: string
  value: string
}

export type ImageSizeResolution = 'auto' | '1K' | '2K' | '4K'

export interface ImageSizePreset extends ImageSizeOption {
  ratio: string
  resolution: ImageSizeResolution
  width?: number
  height?: number
}

function gcd(a: number, b: number): number {
  return b === 0 ? a : gcd(b, a % b)
}

export function parseImageSize(value: string) {
  if (!value || value === DEFAULT_IMAGE_SIZE) return null
  const match = value.match(/^(\d+)\s*x\s*(\d+)$/i)
  if (!match) return null
  const width = Number(match[1])
  const height = Number(match[2])
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  return { width, height }
}

function imageResolutionTier(width: number, height: number): ImageSizeResolution {
  const maxEdge = Math.max(width, height)
  if (maxEdge >= 3840) return '4K'
  if (maxEdge > 1920) return '2K'
  return '1K'
}

export function formatImageSizeLabel(value: string, autoLabel = '自动') {
  if (!value || value === DEFAULT_IMAGE_SIZE) return autoLabel
  const parsed = parseImageSize(value)
  if (!parsed) return value
  const { width, height } = parsed
  const divisor = gcd(width, height)
  const ratio = `${width / divisor}:${height / divisor}`
  return [ratio, imageResolutionTier(width, height), `${width}x${height}`].join(' · ')
}

function createSizePreset(value: string, ratio: string, resolution: ImageSizeResolution): ImageSizePreset {
  const parsed = parseImageSize(value)
  return {
    label: formatImageSizeLabel(value),
    value,
    ratio,
    resolution,
    width: parsed?.width,
    height: parsed?.height,
  }
}

export const STANDARD_IMAGE_SIZE_PRESETS: ImageSizePreset[] = [
  { label: '自动', value: 'auto', ratio: 'auto', resolution: 'auto' },
  createSizePreset('1024x1024', '1:1', '1K'),
  createSizePreset('1024x1536', '2:3', '1K'),
  createSizePreset('1536x1024', '3:2', '1K'),
  createSizePreset('1024x1365', '3:4', '1K'),
  createSizePreset('1365x1024', '4:3', '1K'),
  createSizePreset('1088x1920', '9:16', '1K'),
  createSizePreset('1920x1088', '16:9', '1K'),
]

export const HIGH_RES_IMAGE_SIZE_PRESETS: ImageSizePreset[] = [
  createSizePreset('2048x2048', '1:1', '2K'),
  createSizePreset('2560x1440', '16:9', '2K'),
  createSizePreset('1440x2560', '9:16', '2K'),
  createSizePreset('3840x2160', '16:9', '4K'),
  createSizePreset('2160x3840', '9:16', '4K'),
]

export const IMAGE_SIZE_PRESETS: ImageSizePreset[] = [
  ...STANDARD_IMAGE_SIZE_PRESETS,
  ...HIGH_RES_IMAGE_SIZE_PRESETS,
]

export const STANDARD_IMAGE_SIZE_OPTIONS: ImageSizeOption[] = STANDARD_IMAGE_SIZE_PRESETS
export const HIGH_RES_IMAGE_SIZE_OPTIONS: ImageSizeOption[] = HIGH_RES_IMAGE_SIZE_PRESETS
export const IMAGE_SIZE_OPTIONS: ImageSizeOption[] = IMAGE_SIZE_PRESETS

export function supportsHighResolutionImageSizes(highResolutionEnabled = false) {
  return highResolutionEnabled
}

export function resolveImageSizePresets(highResolutionEnabled = false): ImageSizePreset[] {
  return supportsHighResolutionImageSizes(highResolutionEnabled)
    ? IMAGE_SIZE_PRESETS
    : STANDARD_IMAGE_SIZE_PRESETS
}

export function resolveImageSizeOptions(highResolutionEnabled = false): ImageSizeOption[] {
  return resolveImageSizePresets(highResolutionEnabled)
}

export function isImageSizeSupportedByModel(size: string, highResolutionEnabled = false) {
  if (!size || size === DEFAULT_IMAGE_SIZE) return true
  return resolveImageSizeOptions(highResolutionEnabled).some((option) => option.value === size)
}

export const IMAGE_QUALITY_OPTIONS = [
  { label: '自动', value: 'auto' },
  { label: '低', value: 'low' },
  { label: '中', value: 'medium' },
  { label: '高', value: 'high' },
]

export const IMAGE_COUNT_OPTIONS = [
  { label: '1 张', value: 1 },
  { label: '2 张', value: 2 },
  { label: '3 张', value: 3 },
  { label: '4 张', value: 4 },
]

function cleanString(value: unknown, fallback = '') {
  const text = String(value ?? '').trim()
  return text || fallback
}

export function normalizeImageCount(value: unknown) {
  const count = Number.isFinite(Number(value)) ? Math.trunc(Number(value)) : 1
  return Math.min(4, Math.max(1, count))
}

export function createClientTaskId(prefix = 'img') {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

type JsonObject = Record<string, unknown>

const IMAGE_TASK_STATUSES = new Set<ImageTaskStatus>([
  'queued',
  'running',
  'success',
  'partial_success',
  'failed',
  'text_review',
])

function imageTaskContractError(path: string, expected: string): never {
  throw new Error(`Image task response contract mismatch at ${path}: expected ${expected}`)
}

function expectObject(value: unknown, path: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) imageTaskContractError(path, 'object')
  return value as JsonObject
}

function expectString(value: unknown, path: string): string {
  if (typeof value !== 'string') imageTaskContractError(path, 'string')
  return value
}

function expectBoolean(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') imageTaskContractError(path, 'boolean')
  return value
}

function expectInteger(value: unknown, path: string, minimum = 0): number {
  if (!Number.isInteger(value) || Number(value) < minimum) {
    imageTaskContractError(path, `integer >= ${minimum}`)
  }
  return Number(value)
}

function expectNullableInteger(value: unknown, path: string): number | null {
  if (value === null) return null
  return expectInteger(value, path)
}

function expectImageTaskStatus(value: unknown, path: string): ImageTaskStatus {
  const status = expectString(value, path) as ImageTaskStatus
  if (!IMAGE_TASK_STATUSES.has(status)) imageTaskContractError(path, Array.from(IMAGE_TASK_STATUSES).join(' | '))
  return status
}

function expectImageTaskMode(value: unknown, path: string): ImageTaskMode {
  if (value !== 'generate' && value !== 'edit') imageTaskContractError(path, 'generate | edit')
  return value
}

function parseTaskAsset(value: unknown, path: string): ImageTaskAsset {
  const asset = expectObject(value, path)
  const width = expectNullableInteger(asset.width, `${path}.width`)
  const height = expectNullableInteger(asset.height, `${path}.height`)
  if (width === 0 || height === 0) imageTaskContractError(path, 'positive dimensions or null')
  return {
    url: expectString(asset.url, `${path}.url`),
    path: expectString(asset.path, `${path}.path`),
    b64_json: expectString(asset.b64_json, `${path}.b64_json`),
    revised_prompt: expectString(asset.revised_prompt, `${path}.revised_prompt`),
    width,
    height,
  }
}

function parseImageTask(value: unknown, path = 'response'): ImageTask {
  const raw = expectObject(value, path)
  const status = expectImageTaskStatus(raw.status, `${path}.status`)
  const terminal = expectBoolean(raw.terminal, `${path}.terminal`)
  const results = Array.isArray(raw.results)
    ? raw.results.map((asset, index) => parseTaskAsset(asset, `${path}.results[${index}]`))
    : imageTaskContractError(`${path}.results`, 'array')
  const requestedCount = expectInteger(raw.requested_count, `${path}.requested_count`, 1)
  if (requestedCount > 4) imageTaskContractError(`${path}.requested_count`, 'integer between 1 and 4')
  const succeededCount = expectInteger(raw.succeeded_count, `${path}.succeeded_count`)
  const failedCount = expectInteger(raw.failed_count, `${path}.failed_count`)
  const pendingCount = expectInteger(raw.pending_count, `${path}.pending_count`)
  const expectedTerminal = status !== 'queued' && status !== 'running'
  if (terminal !== expectedTerminal) imageTaskContractError(`${path}.terminal`, `consistent with status ${status}`)
  if (terminal && pendingCount !== 0) imageTaskContractError(`${path}.pending_count`, '0 for terminal task')
  if (!terminal && failedCount !== 0) imageTaskContractError(`${path}.failed_count`, '0 for active task')
  if (succeededCount !== results.length) imageTaskContractError(`${path}.succeeded_count`, 'results.length')

  const actions = expectObject(raw.actions, `${path}.actions`)
  return {
    id: expectString(raw.id, `${path}.id`),
    status,
    terminal,
    mode: expectImageTaskMode(raw.mode, `${path}.mode`),
    model: expectString(raw.model, `${path}.model`),
    size: expectString(raw.size, `${path}.size`),
    quality: expectString(raw.quality, `${path}.quality`),
    stage_code: expectString(raw.stage_code, `${path}.stage_code`),
    stage_label: expectString(raw.stage_label, `${path}.stage_label`),
    created_at: expectString(raw.created_at, `${path}.created_at`),
    updated_at: expectString(raw.updated_at, `${path}.updated_at`),
    requested_count: requestedCount,
    succeeded_count: succeededCount,
    failed_count: failedCount,
    pending_count: pendingCount,
    duration_ms: expectNullableInteger(raw.duration_ms, `${path}.duration_ms`),
    elapsed_ms: expectNullableInteger(raw.elapsed_ms, `${path}.elapsed_ms`),
    error_code: expectString(raw.error_code, `${path}.error_code`),
    public_error: expectString(raw.public_error, `${path}.public_error`),
    results,
    actions: {
      resume_poll: expectBoolean(actions.resume_poll, `${path}.actions.resume_poll`),
    },
  }
}

function parseImageTasksResponse(value: unknown): ImageTasksResponse {
  const response = expectObject(value, 'response')
  if (!Array.isArray(response.items)) imageTaskContractError('response.items', 'array')
  if (!Array.isArray(response.missing_ids)) imageTaskContractError('response.missing_ids', 'string[]')
  return {
    items: response.items.map((item, index) => parseImageTask(item, `response.items[${index}]`)),
    missing_ids: response.missing_ids.map((id, index) => expectString(id, `response.missing_ids[${index}]`)),
  }
}

function requestSize(size?: string) {
  const value = cleanString(size, DEFAULT_IMAGE_SIZE)
  return value === DEFAULT_IMAGE_SIZE ? undefined : value
}

function normalizeUrlList(value: string[] | undefined) {
  return (value || []).map((item) => item.trim()).filter(Boolean)
}

function createEditForm(input: CreateEditTaskInput) {
  const form = new FormData()
  form.append('client_task_id', input.clientTaskId || createClientTaskId('edit'))
  form.append('prompt', input.prompt)
  form.append('model', input.model || DEFAULT_IMAGE_MODEL)
  form.append('n', String(normalizeImageCount(input.n)))
  form.append('quality', input.quality || DEFAULT_IMAGE_QUALITY)
  const size = requestSize(input.size)
  if (size) form.append('size', size)

  const imageUrls = normalizeUrlList(input.imageUrls)
  if (imageUrls.length === 1) {
    form.append('image_url', imageUrls[0])
  } else if (imageUrls.length > 1) {
    form.append('images', JSON.stringify(imageUrls))
  }

  for (const file of input.files || []) {
    form.append('image', file, file.name)
  }
  if (input.mask) {
    form.append('mask', input.mask, input.mask.name || 'mask.png')
  }
  return form
}

export function imageAssetUrl(asset: ImageTaskAsset) {
  const url = cleanString(asset.url)
  if (url) return url
  const base64 = cleanString(asset.b64_json)
  return base64 ? `data:image/png;base64,${base64}` : ''
}

export const imageTasksApi = {
  list: async (ids?: string[]) => {
    const params = ids?.length ? { ids: ids.join(',') } : undefined
    const response = await apiClient.get<never, unknown>('/api/image-tasks', { params })
    return parseImageTasksResponse(response)
  },

  createGeneration: async (input: CreateGenerationTaskInput) => {
    const response = await apiClient.post<Record<string, unknown>, unknown>('/api/image-tasks/generations', {
      client_task_id: input.clientTaskId || createClientTaskId('gen'),
      prompt: input.prompt,
      model: input.model || DEFAULT_IMAGE_MODEL,
      n: normalizeImageCount(input.n),
      size: requestSize(input.size),
      quality: input.quality || DEFAULT_IMAGE_QUALITY,
    })
    return parseImageTask(response)
  },

  createEdit: async (input: CreateEditTaskInput) => {
    const response = await apiClient.post<FormData, unknown>('/api/image-tasks/edits', createEditForm(input))
    return parseImageTask(response)
  },

  resumePoll: async (taskId: string, extraTimeoutSecs = 30) => {
    const response = await apiClient.post<{ extra_timeout_secs: number }, unknown>(
      `/api/image-tasks/${encodeURIComponent(taskId)}/resume-poll`,
      { extra_timeout_secs: extraTimeoutSecs },
    )
    return parseImageTask(response)
  },
}
