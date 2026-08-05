import { readdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = path.join(projectRoot, 'src')
const outputFile = path.join(sourceRoot, 'lib', 'localLucideIcons.generated.ts')
const collectionFile = path.join(
  projectRoot,
  'node_modules',
  '@iconify-json',
  'lucide',
  'icons.json',
)

async function sourceFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const nested = await Promise.all(entries.map(async (entry) => {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(target)
    return /\.(?:ts|vue)$/.test(entry.name) && !entry.name.endsWith('.generated.ts')
      ? [target]
      : []
  }))
  return nested.flat()
}

async function referencedIconNames() {
  const names = new Set()
  for (const file of await sourceFiles(sourceRoot)) {
    const source = await readFile(file, 'utf8')
    for (const match of source.matchAll(/lucide:([a-z0-9-]+)/g)) {
      names.add(match[1])
    }
  }
  return [...names].sort()
}

function buildSubset(collection, requestedNames) {
  const icons = {}
  const aliases = {}

  function include(name) {
    if (Object.hasOwn(icons, name) || Object.hasOwn(aliases, name)) return
    if (Object.hasOwn(collection.icons, name)) {
      icons[name] = collection.icons[name]
      return
    }
    const alias = collection.aliases?.[name]
    if (!alias) throw new Error(`Unknown Lucide icon referenced by the app: ${name}`)
    aliases[name] = alias
    include(alias.parent)
  }

  requestedNames.forEach(include)
  return {
    prefix: collection.prefix,
    ...(collection.width == null ? {} : { width: collection.width }),
    ...(collection.height == null ? {} : { height: collection.height }),
    icons,
    ...(Object.keys(aliases).length ? { aliases } : {}),
  }
}

function generatedSource(collection, requestedNames) {
  const subset = buildSubset(collection, requestedNames)
  return [
    "import type { IconifyJSON } from '@iconify/types'",
    '',
    `export const localLucideIconNames = ${JSON.stringify(requestedNames, null, 2)} as const`,
    '',
    `export const localLucideIcons = ${JSON.stringify(subset, null, 2)} satisfies IconifyJSON`,
    '',
  ].join('\n')
}

const collection = JSON.parse(await readFile(collectionFile, 'utf8'))
const output = generatedSource(collection, await referencedIconNames())

if (process.argv.includes('--check')) {
  const current = await readFile(outputFile, 'utf8').catch(() => '')
  if (current !== output) {
    throw new Error('Local Lucide icon set is stale. Run npm run icons:generate.')
  }
} else {
  await writeFile(outputFile, output, 'utf8')
}
