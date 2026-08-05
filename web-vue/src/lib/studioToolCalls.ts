export interface StudioSearchCallContent {
  content: string
  queries: string[]
}

export function splitStudioSearchCalls(value: unknown): StudioSearchCallContent {
  const source = String(value ?? '')
  const queries: string[] = []
  let cursor = skipWhitespace(source, 0)

  while (source.startsWith('search', cursor)) {
    const callStart = cursor
    cursor = skipWhitespace(source, cursor + 'search'.length)
    if (source[cursor] !== '(') {
      cursor = callStart
      break
    }

    cursor = skipWhitespace(source, cursor + 1)
    const stringEnd = jsonStringEnd(source, cursor)
    if (stringEnd < 0) {
      cursor = callStart
      break
    }

    let query = ''
    try {
      const parsed = JSON.parse(source.slice(cursor, stringEnd))
      if (typeof parsed !== 'string') {
        cursor = callStart
        break
      }
      query = parsed.trim()
    } catch {
      cursor = callStart
      break
    }

    cursor = skipWhitespace(source, stringEnd)
    if (!query || source[cursor] !== ')') {
      cursor = callStart
      break
    }

    if (!queries.includes(query)) queries.push(query)
    cursor = skipWhitespace(source, cursor + 1)
  }

  if (!queries.length) return { content: source, queries }
  return { content: source.slice(cursor), queries }
}

function skipWhitespace(value: string, start: number) {
  let cursor = start
  while (cursor < value.length && /\s/.test(value[cursor])) cursor += 1
  return cursor
}

function jsonStringEnd(value: string, start: number) {
  if (value[start] !== '"') return -1
  let escaped = false
  for (let cursor = start + 1; cursor < value.length; cursor += 1) {
    const character = value[cursor]
    if (escaped) {
      escaped = false
      continue
    }
    if (character === '\\') {
      escaped = true
      continue
    }
    if (character === '"') return cursor + 1
  }
  return -1
}
