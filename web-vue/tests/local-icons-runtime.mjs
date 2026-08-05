import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
let networkCalls = 0

Object.defineProperty(globalThis, 'fetch', {
  configurable: true,
  writable: true,
  value: async () => {
    networkCalls += 1
    throw new Error('Iconify network API must not be used for bundled Lucide icons')
  },
})

try {
  const iconify = await import('@iconify/vue')
  const { registerLocalIcons } = await server.ssrLoadModule('/src/lib/icons.ts')
  const { localLucideIconNames } = await server.ssrLoadModule(
    '/src/lib/localLucideIcons.generated.ts',
  )
  registerLocalIcons()

  for (const name of localLucideIconNames) {
    assert.ok(iconify.getIcon(`lucide:${name}`), `lucide:${name} should be registered locally`)
    await iconify.loadIcon(`lucide:${name}`)
  }
  assert.equal(networkCalls, 0)

  const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  const mainSource = await readFile(path.join(projectRoot, 'src', 'main.ts'), 'utf8')
  assert.match(mainSource, /registerLocalIcons\(\)/)
} finally {
  if (originalFetch) Object.defineProperty(globalThis, 'fetch', originalFetch)
  else delete globalThis.fetch
  await server.close()
}
