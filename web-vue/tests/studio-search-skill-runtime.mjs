import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const {
    buildSearchSkillInstallPrompt,
    loadSearchSkillInstallPrompt,
  } = await server.ssrLoadModule(
    '/src/views/studio/studioSearchSkill.ts',
  )
  const secret = 'must-not-be-copied-admin-key'
  for (const language of ['zh', 'en']) {
    // Deliberately pass a legacy apiKey property as a runtime regression canary.
    // The generated document must ignore it even if an old caller still supplies one.
    const prompt = buildSearchSkillInstallPrompt({
      baseUrl: 'https://api.example.com/',
      apiKey: secret,
      language,
    })

    assert.equal(prompt.includes(secret), false)
    assert.match(prompt, /Authorization: Bearer \$\{CHATGPT2API_API_KEY\}/)
    assert.match(prompt, /https:\/\/api\.example\.com\/v1\/search/)
    assert.match(prompt, /\$env:CHATGPT2API_API_KEY = '<your-api-key>'/)
    assert.match(prompt, /export CHATGPT2API_API_KEY='<your-api-key>'/)
  }

  let runtimeBaseUrl = 'https://console.example.com'
  const runtimePrompt = await loadSearchSkillInstallPrompt({
    language: 'zh',
    getBaseUrl: () => runtimeBaseUrl,
    loadRuntimeConfig: async () => {
      runtimeBaseUrl = 'https://api.example.com'
    },
  })
  assert.match(runtimePrompt, /https:\/\/api\.example\.com\/v1\/search/)
  assert.equal(runtimePrompt.includes('https://console.example.com/v1/search'), false)
} finally {
  await server.close()
}
