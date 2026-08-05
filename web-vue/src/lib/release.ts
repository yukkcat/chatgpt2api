export type ReleaseInfo = {
  version: string
  date: string
  items: { type: string; content: string }[]
}

export type ReleaseInlineSegment = {
  kind: 'text' | 'code'
  content: string
}

export function splitReleaseInlineCode(value: string): ReleaseInlineSegment[] {
  const source = String(value || '')
  const segments: ReleaseInlineSegment[] = []
  const pattern = /`([^`\n]+)`/g
  let cursor = 0

  for (const match of source.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > cursor) {
      segments.push({ kind: 'text', content: source.slice(cursor, index) })
    }
    segments.push({ kind: 'code', content: match[1] })
    cursor = index + match[0].length
  }

  if (cursor < source.length) {
    segments.push({ kind: 'text', content: source.slice(cursor) })
  }
  return segments.length ? segments : [{ kind: 'text', content: source }]
}

export function parseChangelog(content: string): ReleaseInfo[] {
  return content
    .split(/^## /m)
    .slice(1)
    .map((block) => {
      const [title = '', ...lines] = block.trim().split('\n')
      const [, version = title.trim(), date = ''] = title.match(/^(.+?)(?:\s+-\s+(.+))?$/) || []
      return {
        version: version.trim(),
        date: date.trim(),
        items: lines
          .map((line) => line.trim().match(/^\+\s+\[(.+?)]\s+(.+)$/))
          .filter((match): match is RegExpMatchArray => Boolean(match))
          .map((match) => ({ type: match[1], content: match[2] })),
      }
    })
    .filter((release) => release.items.length)
}

export function normalizeVersionTag(value: string): string {
  const clean = value.trim()
  if (!clean) return ''
  return clean.startsWith('v') ? clean : `v${clean}`
}

export function latestReleasedVersion(releases: ReleaseInfo[]): string {
  return releases.find((release) => parseVersion(release.version))?.version || ''
}

type ParsedVersion = {
  core: [number, number, number]
  prerelease: string[]
}

function parseVersion(value: string): ParsedVersion | null {
  const match = value.trim().match(
    /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z.-]+)?$/,
  )
  if (!match) return null
  return {
    core: [Number(match[1]), Number(match[2]), Number(match[3])],
    prerelease: match[4] ? match[4].split('.') : [],
  }
}

function comparePrereleaseIdentifier(left: string, right: string): number {
  const leftIsNumeric = /^\d+$/.test(left)
  const rightIsNumeric = /^\d+$/.test(right)
  if (leftIsNumeric && rightIsNumeric) return Number(left) - Number(right)
  if (leftIsNumeric !== rightIsNumeric) return leftIsNumeric ? -1 : 1
  if (left === right) return 0
  return left < right ? -1 : 1
}

function compareVersions(leftValue: string, rightValue: string): number | null {
  const left = parseVersion(leftValue)
  const right = parseVersion(rightValue)
  if (!left || !right) return null

  for (let index = 0; index < left.core.length; index += 1) {
    if (left.core[index] !== right.core[index]) {
      return left.core[index] - right.core[index]
    }
  }

  if (!left.prerelease.length || !right.prerelease.length) {
    if (left.prerelease.length === right.prerelease.length) return 0
    return left.prerelease.length ? -1 : 1
  }

  const identifierCount = Math.max(left.prerelease.length, right.prerelease.length)
  for (let index = 0; index < identifierCount; index += 1) {
    const leftIdentifier = left.prerelease[index]
    const rightIdentifier = right.prerelease[index]
    if (leftIdentifier === undefined) return -1
    if (rightIdentifier === undefined) return 1
    const comparison = comparePrereleaseIdentifier(leftIdentifier, rightIdentifier)
    if (comparison !== 0) return comparison
  }
  return 0
}

export function isNewerVersion(latestVersion: string, currentVersion: string): boolean {
  const comparison = compareVersions(latestVersion, currentVersion)
  return comparison !== null && comparison > 0
}
