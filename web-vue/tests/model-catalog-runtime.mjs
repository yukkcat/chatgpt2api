import assert from 'node:assert/strict'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

function catalog(imageUpscale, revision) {
  return {
    object: 'model_catalog',
    schema_version: 1,
    generated_at: '2026-08-01T00:00:00Z',
    revision,
    chat_models: ['gpt-4o'],
    image_models: ['gpt-image-2'],
    all_models: ['gpt-4o', 'gpt-image-2'],
    defaults: {
      chat_model: 'gpt-4o',
      image_model: 'gpt-image-2',
    },
    capabilities: {
      image_upscale: imageUpscale,
      high_resolution_image_models: [],
    },
    source: {
      chat: 'config',
      image: 'config',
    },
    openai_models_endpoint: '/v1/models',
  }
}

try {
  const { modelsApi } = await server.ssrLoadModule('/src/api/models.ts')
  const modelCatalog = await server.ssrLoadModule('/src/composables/useModelCatalog.ts')

  let authoritative = catalog(false, 'revision-1')
  modelsApi.catalog = async () => authoritative

  const first = await modelCatalog.loadModelCatalog(true)
  assert.equal(first.capabilities.image_upscale, false)

  authoritative = catalog(true, 'revision-2')
  const second = await modelCatalog.loadModelCatalog(true)
  assert.equal(second.revision, 'revision-2')
  assert.equal(second.capabilities.image_upscale, true)
  assert.deepEqual(modelCatalog.useModelCatalog().catalog.value, second)
} finally {
  await server.close()
}
