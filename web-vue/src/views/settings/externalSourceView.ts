import type { CPAPool, Sub2APIServer } from '@/api/accountImports'

export type CPAForm = {
  name: string
  base_url: string
  secret_key: string
}

export type Sub2APIForm = {
  name: string
  base_url: string
  email: string
  password: string
  api_key: string
  group_id: string
}

export function createCPAForm(pool?: CPAPool | null): CPAForm {
  return {
    name: pool?.name || '',
    base_url: pool?.base_url || '',
    secret_key: '',
  }
}

export function createSub2APIForm(server?: Sub2APIServer | null): Sub2APIForm {
  return {
    name: server?.name || '',
    base_url: server?.base_url || '',
    email: server?.email || '',
    password: '',
    api_key: '',
    group_id: server?.group_id || '',
  }
}

export function buildCPAPayload(form: CPAForm): CPAForm {
  return {
    name: form.name.trim(),
    base_url: form.base_url.trim(),
    secret_key: form.secret_key.trim(),
  }
}

export function buildSub2APIPayload(form: Sub2APIForm): Sub2APIForm {
  return {
    name: form.name.trim(),
    base_url: form.base_url.trim(),
    email: form.email.trim(),
    password: form.password,
    api_key: form.api_key.trim(),
    group_id: form.group_id.trim(),
  }
}

export function hasSub2APICredentials(payload: Pick<Sub2APIForm, 'email' | 'password' | 'api_key'>): boolean {
  return Boolean((payload.email && payload.password) || payload.api_key)
}
