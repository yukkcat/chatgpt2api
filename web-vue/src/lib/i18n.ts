import { ref } from 'vue'
import { nanocatEnUS, nanocatZhCN, setNanocatLocale } from 'nanocat-ui'
import { getStringPreference, preferenceKeys, setStringPreference } from '@/lib/preferences'

// The console sources stay Chinese. English mode rewrites rendered text and a few
// attributes from a Chinese -> English dictionary and restores the original text
// when switching back, so upstream Chinese edits never conflict with translations.

export type UiLanguage = 'en' | 'zh'

type Dictionary = {
  exact: Map<string, string>
  patterns: [RegExp, string][]
}

type Original = { orig: string; cur: string }

const TRANSLATED_ATTRIBUTES = ['placeholder', 'title', 'aria-label', 'alt']
const SKIPPED_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE', 'NOSCRIPT'])
const SKIP_SELECTOR = '[data-i18n-skip],[translate="no"],[contenteditable="true"]'
const CJK = /[\u3400-\u9fff\uff00-\uffef]/
const PLACEHOLDER = /\$(\d+)|\u2039(\d+)\|([^|\u203a]*)\|([^\u203a]*)\u203a/g

export function normalizeLanguage(value: unknown): UiLanguage | null {
  if (value === 'zh' || value === 'en') return value
  return null
}

function detectLanguage(): UiLanguage {
  const stored = normalizeLanguage(getStringPreference(preferenceKeys.uiLanguage))
  if (stored) return stored
  const browser = typeof navigator === 'undefined' ? '' : navigator.language || ''
  return /^zh/i.test(browser) ? 'zh' : 'en'
}

export const uiLanguage = ref<UiLanguage>(detectLanguage())

let dictionary: Dictionary | null = null
let dictionaryLoading: Promise<Dictionary> | null = null
let observer: MutationObserver | null = null
const textOriginals = new WeakMap<Node, Original>()
const attributeOriginals = new WeakMap<Element, Map<string, Original>>()
const resultCache = new Map<string, string>()
// Keep-alive pages can be detached while translated, so track every translated node to restore it later.
const translatedTextNodes = new Set<WeakRef<Node>>()
const translatedElements = new Set<WeakRef<Element>>()

async function loadDictionary(): Promise<Dictionary> {
  if (dictionary) return dictionary
  dictionaryLoading ??= import('@/i18n/enDictionary').then(({ enExact, enPatterns }) => {
    const exact = new Map(Object.entries(enExact))
    const patterns: [RegExp, string][] = []
    for (const [source, replacement] of enPatterns) {
      try {
        patterns.push([new RegExp(source), replacement])
      } catch {
        // Skip patterns the browser cannot compile.
      }
    }
    dictionary = { exact, patterns }
    return dictionary
  })
  return dictionaryLoading
}

function fillReplacement(replacement: string, match: RegExpExecArray, dict: Dictionary): string {
  return replacement.replace(PLACEHOLDER, (_, group: string | undefined, pluralGroup: string | undefined, one: string, many: string) => {
    if (group !== undefined) return translateCore(match[Number(group)] ?? '', dict, false)
    const count = Number((match[Number(pluralGroup)] ?? '').replace(/,/g, ''))
    return count === 1 ? one : many
  })
}

function translateCore(core: string, dict: Dictionary, allowPatterns = true): string {
  const direct = dict.exact.get(core)
  if (direct !== undefined) return direct
  if (!allowPatterns) return core
  for (const [regex, replacement] of dict.patterns) {
    const match = regex.exec(core)
    if (match) return fillReplacement(replacement, match, dict)
  }
  return core
}

function translateString(value: string, dict: Dictionary): string {
  const cached = resultCache.get(value)
  if (cached !== undefined) return cached
  const match = /^(\s*)([\s\S]*?)(\s*)$/.exec(value)
  const core = match?.[2] ?? ''
  let translated = value
  if (core && CJK.test(core)) {
    translated = (match?.[1] ?? '') + translateCore(core, dict) + (match?.[3] ?? '')
  }
  if (resultCache.size > 5000) resultCache.clear()
  resultCache.set(value, translated)
  return translated
}

function isSkipped(node: Node): boolean {
  const element = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement
  if (!element) return true
  if (SKIPPED_TAGS.has(element.tagName)) return true
  return element.closest(SKIP_SELECTOR) !== null
}

function translateTextNode(node: Node, dict: Dictionary): void {
  const value = node.nodeValue ?? ''
  const known = textOriginals.get(node)
  if (known && known.cur === value) return
  if (isSkipped(node)) return
  const translated = translateString(value, dict)
  if (translated === value) {
    textOriginals.delete(node)
    return
  }
  if (!known) {
    if (translatedTextNodes.size > 20000) {
      for (const ref of translatedTextNodes) if (!ref.deref()) translatedTextNodes.delete(ref)
    }
    translatedTextNodes.add(new WeakRef(node))
  }
  textOriginals.set(node, { orig: value, cur: translated })
  node.nodeValue = translated
}

function translateAttributes(element: Element, dict: Dictionary): void {
  if (element.tagName === 'SCRIPT' || element.tagName === 'STYLE' || element.closest(SKIP_SELECTOR)) return
  for (const name of TRANSLATED_ATTRIBUTES) {
    const value = element.getAttribute(name)
    if (!value) continue
    const known = attributeOriginals.get(element)?.get(name)
    if (known && known.cur === value) continue
    const translated = translateString(value, dict)
    if (translated === value) {
      attributeOriginals.get(element)?.delete(name)
      continue
    }
    let map = attributeOriginals.get(element)
    if (!map) {
      map = new Map()
      attributeOriginals.set(element, map)
      translatedElements.add(new WeakRef(element))
    }
    map.set(name, { orig: value, cur: translated })
    element.setAttribute(name, translated)
  }
}

function translateTree(root: Node, dict: Dictionary): void {
  if (root.nodeType === Node.TEXT_NODE) {
    translateTextNode(root, dict)
    return
  }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return
  if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root as Element, dict)
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.nodeType === Node.TEXT_NODE) translateTextNode(node, dict)
    else translateAttributes(node as Element, dict)
  }
}

function restoreTextNode(node: Node): void {
  const known = textOriginals.get(node)
  if (known && node.nodeValue === known.cur) node.nodeValue = known.orig
  textOriginals.delete(node)
}

function restoreElement(element: Element): void {
  const map = attributeOriginals.get(element)
  if (!map) return
  for (const [name, known] of map) {
    if (element.getAttribute(name) === known.cur) element.setAttribute(name, known.orig)
  }
  attributeOriginals.delete(element)
}

function restoreAll(): void {
  for (const ref of translatedTextNodes) {
    const node = ref.deref()
    if (node) restoreTextNode(node)
  }
  for (const ref of translatedElements) {
    const element = ref.deref()
    if (element) restoreElement(element)
  }
  translatedTextNodes.clear()
  translatedElements.clear()
}

function startObserving(dict: Dictionary): void {
  stopObserving()
  const root = document.documentElement
  const options: MutationObserverInit = {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: TRANSLATED_ATTRIBUTES,
  }
  observer = new MutationObserver(records => {
    observer?.disconnect()
    try {
      for (const record of records) {
        if (record.type === 'childList') {
          record.addedNodes.forEach(node => translateTree(node, dict))
        } else if (record.type === 'characterData') {
          translateTextNode(record.target, dict)
        } else if (record.target.nodeType === Node.ELEMENT_NODE) {
          translateAttributes(record.target as Element, dict)
        }
      }
    } finally {
      observer?.observe(root, options)
    }
  })
  observer.observe(root, options)
}

function stopObserving(): void {
  observer?.disconnect()
  observer = null
}

async function applyLanguage(language: UiLanguage): Promise<void> {
  document.documentElement.lang = language === 'en' ? 'en' : 'zh-CN'
  setNanocatLocale(language === 'en' ? nanocatEnUS : nanocatZhCN)
  if (language === 'en') {
    const dict = await loadDictionary()
    if (uiLanguage.value !== 'en') return
    translateTree(document.documentElement, dict)
    startObserving(dict)
    return
  }
  stopObserving()
  restoreAll()
}

export function setUiLanguage(language: UiLanguage): void {
  setStringPreference(preferenceKeys.uiLanguage, language)
  uiLanguage.value = language
  void applyLanguage(language)
}

export function toggleUiLanguage(): void {
  setUiLanguage(uiLanguage.value === 'en' ? 'zh' : 'en')
}

// Loads the dictionary before the first render so English users never see a flash of Chinese.
export async function prepareUiLanguage(): Promise<void> {
  setNanocatLocale(uiLanguage.value === 'en' ? nanocatEnUS : nanocatZhCN)
  if (uiLanguage.value === 'en') await loadDictionary()
}

export function initUiLanguage(): void {
  void applyLanguage(uiLanguage.value)
}
