import { getAuthToken } from '@/api/client'

const apiBaseUrl = String(import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')

function cleanString(value: unknown) {
  return String(value || '').trim()
}

function absoluteUrl(url: string) {
  if (/^(data|blob):/i.test(url)) return url
  return /^https?:\/\//i.test(url)
    ? url
    : new URL(url, window.location.origin).toString()
}

function encodePathSegments(path: string) {
  return cleanString(path)
    .replace(/\\/g, '/')
    .replace(/^\/+/, '')
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/')
}

function localImagePathFromUrl(url: string) {
  const value = cleanString(url)
  if (!value || /^(data|blob):/i.test(value)) return ''

  if (value.startsWith('/images/')) return value.slice('/images/'.length)
  if (value.startsWith('images/')) return value.slice('images/'.length)

  try {
    const parsed = new URL(value, window.location.origin)
    if (parsed.pathname.startsWith('/images/')) {
      return decodeURIComponent(parsed.pathname.slice('/images/'.length))
    }
  } catch {
    return ''
  }

  return ''
}

function filenameWithExtension(filename: string, blob: Blob, sourceUrl: string) {
  const cleanName = cleanString(filename) || 'image'
  if (/\.[a-z0-9]{2,5}$/i.test(cleanName)) return cleanName

  const typeExt = blob.type.includes('jpeg')
    ? 'jpg'
    : blob.type.includes('webp')
      ? 'webp'
      : blob.type.includes('gif')
        ? 'gif'
        : blob.type.includes('png')
          ? 'png'
          : ''
  if (typeExt) return `${cleanName}.${typeExt}`

  try {
    const ext = new URL(sourceUrl, window.location.origin).pathname.match(/\.([a-z0-9]{2,5})$/i)?.[1]
    if (ext) return `${cleanName}.${ext}`
  } catch {
    // Keep the original name when the URL cannot be parsed.
  }

  return cleanName
}

export function saveBlob(blob: Blob, filename: string, sourceUrl = '') {
  const blobUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = blobUrl
  anchor.download = filenameWithExtension(filename, blob, sourceUrl)
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1000)
}

export function downloadFilenameFromUrl(url: string, fallback: string) {
  try {
    const path = new URL(url, window.location.origin).pathname
    const filename = decodeURIComponent(path.split('/').filter(Boolean).pop() || '')
    return filename || fallback
  } catch {
    return fallback
  }
}

async function fetchBlob(url: string, authorization = false) {
  const headers: Record<string, string> = {}
  const token = authorization ? getAuthToken() : ''
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(absoluteUrl(url), {
    headers,
    mode: 'cors',
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)

  const blob = await response.blob()
  if (!blob.size) throw new Error('empty file payload')
  return blob
}

function localDownloadUrl(path: string) {
  const encodedPath = encodePathSegments(path)
  if (!encodedPath) return ''
  return `${apiBaseUrl}/api/images/download/${encodedPath}`
}

export async function downloadUrlAsFile(
  url: string,
  filename: string,
  options: { localPath?: string } = {},
) {
  const value = cleanString(url)
  if (!value) throw new Error('missing image URL')

  const localPath = cleanString(options.localPath) || localImagePathFromUrl(value)
  if (localPath) {
    const endpoint = localDownloadUrl(localPath)
    if (endpoint) {
      try {
        const blob = await fetchBlob(endpoint, true)
        saveBlob(blob, filename, endpoint)
        return
      } catch {
        // Some user-key sessions cannot access the admin download endpoint.
        // Fall through to public image fetch without opening a new tab.
      }
    }
  }

  try {
    const blob = await fetchBlob(value)
    saveBlob(blob, filename, value)
  } catch (error: any) {
    throw new Error(error?.message || 'image source is not readable by the browser')
  }
}

export async function downloadPublicUrlAsFile(url: string, filename: string) {
  const value = cleanString(url)
  if (!value) throw new Error('missing file URL')

  try {
    const blob = await fetchBlob(value)
    saveBlob(blob, filename, value)
  } catch (error: any) {
    throw new Error(error?.message || 'file source is not readable by the browser')
  }
}
