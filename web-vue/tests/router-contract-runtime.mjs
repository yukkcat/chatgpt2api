import assert from 'node:assert/strict'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createServer } from 'vite'

const server = await createServer({
  appType: 'custom',
  logLevel: 'silent',
  server: { middlewareMode: true },
})

function replaceLazyComponents(routes) {
  return routes.map((route) => ({
    ...route,
    ...(route.component ? { component: {} } : {}),
    ...(route.children ? { children: replaceLazyComponents(route.children) } : {}),
  }))
}

try {
  const { appRoutes, matchedRoutesRequireAuth, resolveLoginRedirect } = await server.ssrLoadModule(
    '/src/router/routes.ts',
  )
  const router = createRouter({
    history: createMemoryHistory(),
    routes: replaceLazyComponents(appRoutes),
  })

  const login = router.resolve('/login')
  assert.equal(matchedRoutesRequireAuth(login.matched), false)
  assert.equal(resolveLoginRedirect('/logs?page=2', '/'), '/logs?page=2')
  assert.equal(resolveLoginRedirect(['/studio'], '/'), '/studio')
  assert.equal(resolveLoginRedirect('https://example.com', '/studio'), '/studio')
  assert.equal(resolveLoginRedirect('//example.com', '/studio'), '/studio')
  assert.equal(resolveLoginRedirect('/login?redirect=/logs', '/studio'), '/studio')

  const legacyDebug = router.resolve('/debug')
  assert.equal(matchedRoutesRequireAuth(legacyDebug.matched), true)
  await router.push('/debug')
  assert.equal(router.currentRoute.value.fullPath, '/studio')
  assert.equal(router.currentRoute.value.meta.requiredCapability, 'studio')

  const unknown = router.resolve('/removed-or-mistyped-route')
  assert.equal(matchedRoutesRequireAuth(unknown.matched), true)
  await router.push('/removed-or-mistyped-route')
  assert.equal(router.currentRoute.value.fullPath, '/')
  assert.equal(router.currentRoute.value.name, 'dashboard')
  assert.equal(router.currentRoute.value.meta.requiredCapability, 'admin_console')
} finally {
  await server.close()
}
