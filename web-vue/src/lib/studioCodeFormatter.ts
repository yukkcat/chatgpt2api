import type { StudioCodeFormatter } from '@/lib/studioMarkdownRenderer'

let formatterPromise: Promise<StudioCodeFormatter> | null = null

export function loadStudioCodeFormatter() {
  formatterPromise ||= import('@/lib/studioCodeFormatterRuntime').then((module) => module.formatStudioCode)
  return formatterPromise
}
