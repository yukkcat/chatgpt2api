import hljs from 'highlight.js/lib/core'
import bash from 'highlight.js/lib/languages/bash'
import css from 'highlight.js/lib/languages/css'
import javascript from 'highlight.js/lib/languages/javascript'
import json from 'highlight.js/lib/languages/json'
import markdown from 'highlight.js/lib/languages/markdown'
import python from 'highlight.js/lib/languages/python'
import shell from 'highlight.js/lib/languages/shell'
import sql from 'highlight.js/lib/languages/sql'
import typescript from 'highlight.js/lib/languages/typescript'
import xml from 'highlight.js/lib/languages/xml'
import yaml from 'highlight.js/lib/languages/yaml'
import type { LanguageFn } from 'highlight.js'

const languageAliases: Record<string, string> = {
  console: 'shell',
  html: 'xml',
  js: 'javascript',
  jsonc: 'json',
  md: 'markdown',
  plaintext: 'text',
  powershell: 'shell',
  ps1: 'shell',
  py: 'python',
  sh: 'shell',
  text: 'text',
  ts: 'typescript',
  tsx: 'typescript',
  vue: 'xml',
  yml: 'yaml',
  zsh: 'shell',
}

const languages: Record<string, LanguageFn> = {
  bash,
  css,
  javascript,
  json,
  markdown,
  python,
  shell,
  sql,
  typescript,
  xml,
  yaml,
}

let registered = false

export function highlightStudioCode(code: string, language: string | undefined) {
  const normalized = normalizeStudioLanguage(language)
  if (!normalized || normalized === 'text' || !languages[normalized]) return escapeHtml(code)

  registerStudioLanguages()
  try {
    return hljs.highlight(code, { language: normalized, ignoreIllegals: true }).value
  } catch {
    return escapeHtml(code)
  }
}

function registerStudioLanguages() {
  if (registered) return
  for (const [name, language] of Object.entries(languages)) {
    hljs.registerLanguage(name, language)
  }
  registered = true
}

function normalizeStudioLanguage(language: string | undefined) {
  const value = String(language || '').trim().toLowerCase().replace(/^language-/, '')
  return languageAliases[value] || value
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}
