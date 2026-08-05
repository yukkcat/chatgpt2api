import apiClient from './client'

export interface ModelCatalogResponse {
  object: 'model_catalog'
  schema_version: 1
  generated_at: string
  revision: string
  chat_models: string[]
  image_models: string[]
  all_models: string[]
  defaults: {
    chat_model: string
    image_model: string
  }
  capabilities: {
    image_upscale: boolean
    high_resolution_image_models: string[]
  }
  source: {
    chat: 'config' | 'accounts' | 'fallback'
    image: 'config' | 'accounts' | 'fallback'
  }
  openai_models_endpoint: '/v1/models'
}

export const modelsApi = {
  catalog: () => apiClient.get<never, ModelCatalogResponse>('/api/model-catalog'),
}
