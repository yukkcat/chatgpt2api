import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const staticDir = path.resolve(__dirname, '../../static')
const assetsDir = path.join(staticDir, 'assets')
const indexFile = path.join(staticDir, 'index.html')

function safeRemove(targetPath) {
  if (!fs.existsSync(targetPath)) {
    return
  }
  fs.rmSync(targetPath, { recursive: true, force: true })
}

safeRemove(assetsDir)
safeRemove(indexFile)

fs.mkdirSync(staticDir, { recursive: true })
console.log(`[clean-static] cleaned: ${assetsDir}`)
