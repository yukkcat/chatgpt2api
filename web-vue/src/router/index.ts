import { createRouter, createWebHashHistory } from 'vue-router'
import type { AuthCapability } from '@/api/auth'
import { appRoutes, matchedRoutesRequireAuth, resolveLoginRedirect } from '@/router/routes'
import { useAuthStore } from '@/stores/auth'

function routeCapability(value: unknown): AuthCapability | null {
  return value === 'admin_console' || value === 'studio' ? value : null
}

const router = createRouter({
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes: appRoutes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  if (to.name === 'login') {
    const redirect = resolveLoginRedirect(to.query.redirect, authStore.homeRoute)
    if (authStore.isLoggedIn) {
      return redirect
    }
    const loggedIn = await authStore.checkAuth()
    if (loggedIn) {
      return redirect
    }
    return true
  }

  const requiresAuth = matchedRoutesRequireAuth(to.matched)
  if (!requiresAuth) {
    return true
  }

  const loggedIn = authStore.isLoggedIn || await authStore.checkAuth()
  if (!loggedIn) {
    const redirect = to.fullPath || '/'
    return { name: 'login', query: { redirect } }
  }

  const requiredCapability = to.matched
    .map(record => routeCapability(record.meta.requiredCapability))
    .find((capability): capability is AuthCapability => capability !== null)
  if (requiredCapability && !authStore.hasCapability(requiredCapability)) {
    return authStore.homeRoute
  }

  // Fast path: don't block route switch on auth probe.
  void authStore.checkAuth()

  return true
})

export default router
