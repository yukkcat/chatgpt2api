import type { RouteRecordRaw } from 'vue-router'

export const appRoutes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false },
  },
  {
    path: '/debug',
    redirect: { name: 'studio' },
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppShell.vue'),
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { requiredCapability: 'admin_console' },
      },
      {
        path: 'accounts',
        name: 'accounts',
        component: () => import('@/views/Accounts.vue'),
        meta: { requiredCapability: 'admin_console', management: true },
      },
      {
        path: 'settings',
        name: 'settings',
        component: () => import('@/views/Settings.vue'),
        meta: { requiredCapability: 'admin_console' },
      },
      {
        path: 'proxy',
        name: 'proxy',
        component: () => import('@/views/Proxy.vue'),
        meta: { requiredCapability: 'admin_console' },
      },
      {
        path: 'logs',
        name: 'logs',
        component: () => import('@/views/Logs.vue'),
        meta: { requiredCapability: 'admin_console', management: true },
      },
      {
        path: 'monitor',
        name: 'monitor',
        component: () => import('@/views/Monitor.vue'),
        meta: { requiredCapability: 'admin_console' },
      },
      {
        path: 'gallery',
        name: 'gallery',
        component: () => import('@/views/Gallery.vue'),
        meta: { requiredCapability: 'admin_console', management: true },
      },
      {
        path: 'studio',
        name: 'studio',
        component: () => import('@/views/Studio.vue'),
        meta: { requiredCapability: 'studio', workspace: true },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/',
    meta: { requiresAuth: true },
  },
]

export function matchedRoutesRequireAuth(matched: readonly { meta: { requiresAuth?: boolean } }[]) {
  return matched.some(record => record.meta.requiresAuth !== false)
}

export function resolveLoginRedirect(value: unknown, fallback: string) {
  const candidate = Array.isArray(value) ? value[0] : value
  if (typeof candidate !== 'string') return fallback
  const target = candidate.trim()
  if (!target.startsWith('/') || target.startsWith('//')) return fallback
  if (target === '/login' || target.startsWith('/login?') || target.startsWith('/login#')) return fallback
  return target
}
