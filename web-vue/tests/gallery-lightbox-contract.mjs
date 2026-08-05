import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = await readFile(
  new URL('../src/components/ai/GalleryLightbox.vue', import.meta.url),
  'utf8',
)

assert.match(source, /<ModalShell/)
assert.match(source, /:open="Boolean\(file\)"/)
assert.match(source, /aria-label="图片预览"/)
assert.match(source, /close-on-overlay/)
assert.match(source, /close-on-escape/)
assert.match(source, /@close="emit\('close'\)"/)
assert.match(source, /import \{ CloseButton, ModalShell \} from 'nanocat-ui'/)
assert.doesNotMatch(source, /<Teleport\b/)
