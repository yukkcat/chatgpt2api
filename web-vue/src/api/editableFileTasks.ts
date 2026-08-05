import apiClient from './client'

export type EditableFileKind = 'ppt' | 'psd'
export type EditableFileTaskStatus = 'queued' | 'running' | 'success' | 'error'
export type EditableFileTaskTone = 'muted' | 'warning' | 'success' | 'danger'

export interface EditableFileTaskResult {
  conversation_id: string
  primary_url?: string
  zip_url?: string
}

interface EditableFileTaskBase {
  id: string
  kind: EditableFileKind
  status_label: string
  status_tone: EditableFileTaskTone
  status_icon: string
  is_active: boolean
  created_at: string
  updated_at: string
  elapsed_seconds: number
  can_download: boolean
  can_delete: boolean
}

export type EditableFileTask =
  | (EditableFileTaskBase & {
      status: 'queued' | 'running'
      result?: never
      error?: never
    })
  | (EditableFileTaskBase & {
      status: 'success'
      result: EditableFileTaskResult
      error?: never
    })
  | (EditableFileTaskBase & {
      status: 'error'
      error: string
      result?: never
    })

export interface EditableFileTasksResponse {
  items: EditableFileTask[]
  missing_ids: string[]
}

export interface EditableFileTaskDeleteResponse {
  task_id: string
  deleted: boolean
}

export interface CreateEditableFileTaskInput {
  kind: EditableFileKind
  prompt: string
  base64Images?: string[]
  clientTaskId?: string
}

type JsonObject = Record<string, unknown>

const EDITABLE_FILE_TASK_STATUSES = new Set<EditableFileTaskStatus>([
  'queued',
  'running',
  'success',
  'error',
])

function contractError(path: string, expected: string): never {
  throw new Error(`Editable file task response contract mismatch at ${path}: expected ${expected}`)
}

function expectObject(value: unknown, path: string): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) contractError(path, 'object')
  return value as JsonObject
}

function expectString(value: unknown, path: string): string {
  if (typeof value !== 'string') contractError(path, 'string')
  return value
}

function optionalString(value: unknown, path: string): string | undefined {
  if (value === undefined || value === null || value === '') return undefined
  return expectString(value, path)
}

function expectBoolean(value: unknown, path: string): boolean {
  if (typeof value !== 'boolean') contractError(path, 'boolean')
  return value
}

function expectTone(value: unknown, path: string): EditableFileTaskTone {
  if (value !== 'muted' && value !== 'warning' && value !== 'success' && value !== 'danger') {
    contractError(path, 'muted | warning | success | danger')
  }
  return value
}

function expectNonNegativeInteger(value: unknown, path: string): number {
  if (!Number.isInteger(value) || Number(value) < 0) contractError(path, 'integer >= 0')
  return Number(value)
}

function expectKind(value: unknown, path: string): EditableFileKind {
  if (value !== 'ppt' && value !== 'psd') contractError(path, 'ppt | psd')
  return value
}

function expectStatus(value: unknown, path: string): EditableFileTaskStatus {
  const status = expectString(value, path) as EditableFileTaskStatus
  if (!EDITABLE_FILE_TASK_STATUSES.has(status)) {
    contractError(path, Array.from(EDITABLE_FILE_TASK_STATUSES).join(' | '))
  }
  return status
}

function parseResult(value: unknown, path: string): EditableFileTaskResult {
  const result = expectObject(value, path)
  return {
    conversation_id: expectString(result.conversation_id, `${path}.conversation_id`),
    primary_url: optionalString(result.primary_url, `${path}.primary_url`),
    zip_url: optionalString(result.zip_url, `${path}.zip_url`),
  }
}

function parseTask(value: unknown, path = 'response'): EditableFileTask {
  const raw = expectObject(value, path)
  const id = expectString(raw.id, `${path}.id`)
  if (!id) contractError(`${path}.id`, 'non-empty string')

  const base: EditableFileTaskBase = {
    id,
    kind: expectKind(raw.kind, `${path}.kind`),
    status_label: expectString(raw.status_label, `${path}.status_label`),
    status_tone: expectTone(raw.status_tone, `${path}.status_tone`),
    status_icon: expectString(raw.status_icon, `${path}.status_icon`),
    is_active: expectBoolean(raw.is_active, `${path}.is_active`),
    created_at: expectString(raw.created_at, `${path}.created_at`),
    updated_at: expectString(raw.updated_at, `${path}.updated_at`),
    elapsed_seconds: expectNonNegativeInteger(raw.elapsed_seconds, `${path}.elapsed_seconds`),
    can_download: expectBoolean(raw.can_download, `${path}.can_download`),
    can_delete: expectBoolean(raw.can_delete, `${path}.can_delete`),
  }
  const status = expectStatus(raw.status, `${path}.status`)
  const expectedActive = status === 'queued' || status === 'running'
  if (base.is_active !== expectedActive) {
    contractError(`${path}.is_active`, `consistent with status ${status}`)
  }

  if (status === 'success') {
    return { ...base, status, result: parseResult(raw.result, `${path}.result`) }
  }
  if (status === 'error') {
    return { ...base, status, error: expectString(raw.error, `${path}.error`) }
  }
  return { ...base, status }
}

function parseTasksResponse(value: unknown): EditableFileTasksResponse {
  const response = expectObject(value, 'response')
  if (!Array.isArray(response.items)) contractError('response.items', 'array')
  if (!Array.isArray(response.missing_ids)) contractError('response.missing_ids', 'string[]')
  return {
    items: response.items.map((item, index) => parseTask(item, `response.items[${index}]`)),
    missing_ids: response.missing_ids.map((id, index) => expectString(id, `response.missing_ids[${index}]`)),
  }
}

function parseDeleteResponse(value: unknown, taskId: string): EditableFileTaskDeleteResponse {
  const response = expectObject(value, 'response')
  const deletedTaskId = expectString(response.task_id, 'response.task_id')
  if (!deletedTaskId || deletedTaskId !== taskId) {
    contractError('response.task_id', 'same non-empty value as requested task id')
  }
  const deleted = expectBoolean(response.deleted, 'response.deleted')
  if (!deleted) contractError('response.deleted', 'true')
  return { task_id: deletedTaskId, deleted }
}

function createClientTaskId(kind: EditableFileKind) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${kind}-${crypto.randomUUID()}`
  }
  return `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export const editableFileTasksApi = {
  create: async (input: CreateEditableFileTaskInput) => {
    const response = await apiClient.post<Record<string, unknown>, unknown>('/v1/editable-file-tasks', {
      kind: input.kind,
      prompt: input.prompt,
      base64_images: input.base64Images || [],
      client_task_id: input.clientTaskId || createClientTaskId(input.kind),
    })
    return parseTask(response)
  },

  list: async (ids?: string[], limit = 0) => {
    const params: Record<string, string | number> = {}
    if (ids?.length) params.ids = ids.join(',')
    if (limit > 0) params.limit = limit
    const response = await apiClient.get<never, unknown>('/v1/editable-file-tasks', { params })
    return parseTasksResponse(response)
  },

  delete: async (taskId: string) => {
    const response = await apiClient.delete<never, unknown>(
      `/v1/editable-file-tasks/${encodeURIComponent(taskId)}`,
    )
    return parseDeleteResponse(response, taskId)
  },
}
