import apiClient from './client'
import type { VersionCheckResponse, VersionInfoResponse } from '@/types/api'

function toVersionInfo(payload: { version?: string }): VersionInfoResponse {
  const version = String(payload.version || '').trim()
  return {
    version,
    tag: version.startsWith('v') ? version : `v${version}`,
    commit: '',
  }
}

export const versionApi = {
  async current() {
    const payload = await apiClient.get<never, { version: string }>('/version')
    return toVersionInfo(payload)
  },

  async check(): Promise<VersionCheckResponse> {
    const current = await this.current()
    return {
      ...current,
      repository: 'yukkcat/chatgpt2api',
      latest_tag: current.tag,
      latest_version: current.version,
      release_url: 'https://github.com/yukkcat/chatgpt2api/releases',
      is_latest: true,
      update_available: false,
    }
  },
}
