import beautify from 'js-beautify'
import type { StudioCodeFormatter } from '@/lib/studioMarkdownRenderer'

const MAX_FORMAT_CODE_LENGTH = 200_000

export const formatStudioCode: StudioCodeFormatter = (code) => {
  if (code.length > MAX_FORMAT_CODE_LENGTH) return code
  return beautify.html(code, {
    indent_size: 2,
    preserve_newlines: false,
    max_preserve_newlines: 1,
    wrap_line_length: 120,
    indent_inner_html: true,
    indent_head_inner_html: true,
    indent_body_inner_html: true,
    indent_scripts: 'normal',
    extra_liners: [],
  })
}
