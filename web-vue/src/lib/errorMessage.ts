export type ErrorMessageOptions = {
  fallback?: string
  status?: number
}

function cleanString(value: unknown) {
  return String(value ?? '').trim()
}

function normalizeGenericServerError(message: string, status?: number) {
  const raw = cleanString(message)
  if (
    status
    && status >= 500
    && (
      !raw
      || /^internal server error$/i.test(raw)
      || /^request failed with status code 5\d\d$/i.test(raw)
    )
  ) {
    return `服务器内部错误（HTTP ${status}），请查看后端日志`
  }
  return raw
}

function detailListMessage(items: unknown[], status?: number): string {
  return items
    .map((item) => {
      if (typeof item === 'string') return cleanString(item)
      if (!item || typeof item !== 'object') return ''
      const value = item as Record<string, unknown>
      const message = cleanString(value.msg || value.message)
      if (!message) return ''
      const loc = Array.isArray(value.loc)
        ? value.loc.map((part) => cleanString(part)).filter(Boolean).join('.')
        : cleanString(value.loc)
      return loc ? `${loc}: ${message}` : message
    })
    .filter(Boolean)
    .slice(0, 3)
    .map((message) => normalizeGenericServerError(message, status))
    .join('; ')
}

function objectMessage(value: Record<string, unknown>, status?: number): string {
  const detail = value.detail
  if (typeof detail === 'string') return normalizeGenericServerError(detail, status)
  if (Array.isArray(detail)) return detailListMessage(detail, status)
  if (detail && typeof detail === 'object') {
    const nested = detail as Record<string, unknown>
    if (typeof nested.error === 'string') return normalizeGenericServerError(nested.error, status)
    if (typeof nested.message === 'string') return normalizeGenericServerError(nested.message, status)
  }

  const error = value.error
  if (typeof error === 'string') return normalizeGenericServerError(error, status)
  if (error && typeof error === 'object') {
    const nested = error as Record<string, unknown>
    if (typeof nested.message === 'string') return normalizeGenericServerError(nested.message, status)
  }

  if (typeof value.message === 'string') return normalizeGenericServerError(value.message, status)
  return ''
}

export function errorMessage(error: unknown, options: ErrorMessageOptions | string = {}): string {
  const config: ErrorMessageOptions = typeof options === 'string' ? { fallback: options } : options
  const fallback = config.fallback === undefined ? '请求失败' : cleanString(config.fallback)
  const explicitStatus = config.status
  const status = explicitStatus
    || (error && typeof error === 'object' && 'status' in error ? Number((error as { status?: unknown }).status) || undefined : undefined)
  let message = ''

  if (error && typeof error === 'object') {
    const value = error as Record<string, unknown>
    if (value.data && typeof value.data === 'object') {
      message = objectMessage(value.data as Record<string, unknown>, status)
    }
    message = message || objectMessage(value, status)
  }
  if (!message && error instanceof Error && error.message) {
    message = normalizeGenericServerError(error.message, status)
  } else if (!message && typeof error === 'string') {
    message = normalizeGenericServerError(error, status)
  }

  return message || fallback
}

export function prefixedErrorMessage(prefix: string, error: unknown, fallback = '请求失败') {
  const message = errorMessage(error, fallback)
  return prefix ? `${prefix}: ${message}` : message
}
