<template>
  <div class="app-shell min-h-screen">
    <Transition name="route-progress">
      <div
        v-if="routeProgressPhase !== 'idle'"
        class="shell-route-progress pointer-events-none fixed inset-x-0 top-0 z-[70] h-0.5 overflow-hidden"
        role="progressbar"
        aria-label="Loading page"
      >
        <div
          class="shell-route-progress-bar h-full w-full bg-primary"
          :class="{ 'shell-route-progress-bar--finishing': routeProgressPhase === 'finishing' }"
        ></div>
      </div>
    </Transition>
    <div class="flex min-h-screen flex-col lg:flex-row">
      <div
        v-if="isSidebarOpen && isMobileViewport"
        class="fixed inset-0 z-30 bg-black/20 lg:hidden"
        aria-hidden="true"
        @click="closeSidebar"
      ></div>
      <aside
        ref="sidebarRef"
        class="shell-sidebar fixed inset-y-0 left-0 z-40 w-64 -translate-x-full overflow-hidden bg-card border-r border-border
               transition-[transform,width] duration-200 ease-out will-change-[transform,width] transform-gpu flex flex-col lg:static lg:translate-x-0 lg:w-[var(--sidebar-width)] lg:bg-card
               lg:border-b-0 lg:border-r lg:sticky lg:top-0 lg:h-screen"
        :class="[isSidebarOpen ? 'translate-x-0' : '', { 'sidebar--rail': isSidebarRail }]"
        :style="sidebarStyle"
        :aria-hidden="isMobileViewport && !isSidebarOpen ? 'true' : undefined"
        :inert="isMobileViewport && !isSidebarOpen"
        tabindex="-1"
        @keydown="handleSidebarKeydown"
      >
        <div class="flex h-16 items-center px-5 pt-4 lg:h-20 lg:pt-5">
          <div class="flex min-w-0 items-center">
            <a
              href="https://github.com/yukkcat/chatgpt2api"
              target="_blank"
              rel="noopener noreferrer"
              class="shell-sidebar-brand shrink-0 text-foreground transition-colors hover:text-primary"
              aria-label="GitHub"
            >
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                class="h-6 w-6"
                fill="currentColor"
              >
                <path d="M12 2C6.477 2 2 6.477 2 12c0 4.419 2.865 8.166 6.839 9.489.5.09.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.604-3.369-1.341-3.369-1.341-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.004.071 1.532 1.031 1.532 1.031.892 1.529 2.341 1.087 2.91.832.091-.647.349-1.087.636-1.337-2.22-.253-4.555-1.11-4.555-4.944 0-1.092.39-1.987 1.029-2.687-.103-.253-.446-1.272.098-2.65 0 0 .84-.269 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.026 2.748-1.026.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.687 0 3.842-2.338 4.687-4.566 4.936.359.309.678.919.678 1.852 0 1.337-.012 2.418-.012 2.747 0 .268.18.577.688.479A10.002 10.002 0 0 0 22 12c0-5.523-4.477-10-10-10z" />
              </svg>
            </a>
            <div class="sidebar-label sidebar-brand-label">
              <p class="ui-section-title">ChatGPT2API</p>
            </div>
          </div>
        </div>

        <nav id="app-sidebar-navigation" class="sidebar-nav-scroll min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-2 pb-2 pt-3 lg:pt-4">
          <p class="shell-sidebar-section-label sidebar-section-label px-3 text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Navigation
          </p>
          <div class="space-y-1">
            <RouterLink
              v-for="item in visibleMenuItems"
              :key="item.path"
              :to="item.path"
              class="shell-nav-item group flex items-center overflow-hidden rounded-lg border border-transparent py-1.5 text-sm font-medium transition-colors"
              :class="navItemClassMap[item.path]"
              :aria-label="item.label"
              :aria-current="isNavActive(item.path) ? 'page' : undefined"
              :aria-busy="isNavPending(item.path) ? 'true' : undefined"
              @mouseenter="prefetchRouteView(item.path)"
              @focus="prefetchRouteView(item.path)"
              @click="handleNavClick(item.path)"
            >
              <Tooltip v-if="isSidebarRail" :text="item.label" placement="right">
                <span
                  class="shell-nav-icon inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-colors"
                  :class="navIconClassMap[item.path]"
                >
                  <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                    <path :d="item.icon" />
                  </svg>
                </span>
              </Tooltip>
              <span
                v-else
                class="shell-nav-icon inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-colors"
                :class="navIconClassMap[item.path]"
              >
                <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
                  <path :d="item.icon" />
                </svg>
              </span>
              <span class="sidebar-label">{{ item.label }}</span>
            </RouterLink>
          </div>
        </nav>

        <div class="shell-sidebar-footer mt-auto border-t border-border px-2 py-3">
          <div class="sidebar-footer-actions">
            <Button
              size="sm"
              variant="outline"
              :icon-only="isSidebarRail"
              root-class="sidebar-logout shell-sidebar-footer-button rounded-full text-muted-foreground"
              aria-label="Sign out"
              @click="handleLogout"
            >
              <Tooltip v-if="isSidebarRail" text="Sign out" placement="right">
                <span class="sidebar-footer-tooltip-trigger">
                  <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10 17l5-5-5-5" />
                    <path d="M15 12H3" />
                    <path d="M21 19V5a2 2 0 0 0-2-2h-6" />
                  </svg>
                </span>
              </Tooltip>
              <span class="sidebar-label sidebar-logout-label">Sign out</span>
            </Button>
            <Button
              v-if="!isImmersivePage"
              size="sm"
              variant="outline"
              icon-only
              root-class="sidebar-collapse-button shell-sidebar-footer-button shrink-0 rounded-full text-muted-foreground"
              @click="isSidebarCollapsed = !isSidebarCollapsed"
              :aria-label="isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
              :aria-expanded="!isSidebarCollapsed"
              aria-controls="app-sidebar-navigation"
            >
              <Tooltip v-if="isSidebarRail" :text="isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'" placement="right">
                <span class="sidebar-footer-tooltip-trigger">
                  <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4 shrink-0" fill="currentColor">
                    <path d="M6 4h2v16H6V4zm4 4h8v2h-8V8zm0 6h8v2h-8v-2z" />
                  </svg>
                </span>
              </Tooltip>
              <svg v-else aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4 shrink-0" fill="currentColor">
                <path d="M6 4h2v16H6V4zm4 4h8v2h-8V8zm0 6h8v2h-8v-2z" />
              </svg>
            </Button>
          </div>
        </div>
      </aside>

      <main
        class="relative min-w-0 flex-1 bg-card lg:ml-0"
        :class="[
          { 'flex h-dvh min-h-0 flex-col overflow-hidden': isWorkspacePage },
          { 'lg:flex lg:h-dvh lg:min-h-0 lg:flex-col lg:overflow-hidden': isContainedManagementPage },
        ]"
        :aria-hidden="isMobileSidebarActive ? 'true' : undefined"
        :inert="isMobileSidebarActive"
      >
        <header
          v-if="!isImmersivePage"
          class="shell-header min-w-0 flex h-14 items-center gap-2.5 border-b border-border bg-card px-4 sm:px-6 lg:h-16"
          :class="{ 'shrink-0': usesViewportLayout }"
        >
          <div class="flex min-w-0 flex-1 items-center gap-2.5">
            <Button
              ref="sidebarToggleRef"
              size="xs"
              variant="outline"
              icon-only
              root-class="lg:hidden"
              @click="openSidebar"
              aria-label="Open navigation"
              :aria-expanded="isMobileViewport && isSidebarOpen"
              aria-controls="app-sidebar-navigation"
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" class="h-5 w-5" fill="currentColor">
                <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h16v2H4v-2z" />
              </svg>
            </Button>
            <svg
              aria-hidden="true"
              viewBox="0 0 130 150"
              class="logo-mark hidden h-9 w-9 shrink-0 text-foreground sm:block"
            >
              <defs>
                <filter id="head-shadow" x="-50%" y="-50%" width="200%" height="200%">
                  <feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="rgba(0, 188, 212, 0.2)"/>
                </filter>
              </defs>
              <g class="logo-cat-wrapper" transform="translate(0, 12)">
                <g transform="translate(16, 20) rotate(-10, 9, 12)">
                  <path d="M14 0 L18 24 L0 24 Z" fill="#2c3e50" />
                </g>
                <g transform="translate(96, 20) rotate(10, 9, 12)">
                  <path d="M4 0 L18 24 L0 24 Z" fill="#2c3e50" />
                </g>
                <g filter="url(#head-shadow)">
                  <path d="M 32 40 L 98 40 A 12 12 0 0 1 110 52 L 110 90 A 30 30 0 0 1 80 120 L 50 120 A 30 30 0 0 1 20 90 L 20 52 A 12 12 0 0 1 32 40 Z"
                    fill="rgba(255, 255, 255, 0.9)"
                    stroke="#2c3e50"
                    stroke-width="3"
                  />
                </g>
                <rect class="logo-eye" x="35" y="68" width="14" height="4" rx="1" />
                <rect class="logo-eye" x="81" y="68" width="14" height="4" rx="1" />
              </g>
            </svg>
            <div class="min-w-0">
              <h2 class="truncate text-base font-semibold text-foreground sm:text-lg lg:text-xl">
                {{ currentPageTitle }}
              </h2>
            </div>
          </div>
          <div class="ml-auto flex shrink-0 items-center gap-[12px]">
            <div class="flex items-center gap-[8px]">
              <Tooltip :text="themeButtonTitle" placement="bottom">
                <Button
                  size="sm"
                  variant="outline"
                  :aria-label="themeButtonTitle"
                  @click="cycleThemeMode"
                >
                  {{ themeButtonText }}
                </Button>
              </Tooltip>
              <span v-if="canvasHref" class="hidden lg:inline-flex">
                <Tooltip text="Open infinite canvas" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="Open infinite canvas"
                    @click="openInfiniteCanvas"
                  >
                    Canvas
                  </Button>
                </Tooltip>
              </span>
              <Tooltip text="Refresh this page" placement="bottom">
                <Button
                  size="sm"
                  variant="outline"
                  aria-label="Refresh this page"
                  @click="refreshPage"
                >
                  Refresh
                </Button>
              </Tooltip>
            </div>
            <div class="flex items-center gap-[8px]">
              <span v-if="authStore.isAdmin" class="hidden lg:inline-flex">
                <Tooltip text="View API information" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="View API information"
                    @click="openApiInfo"
                  >
                    API
                  </Button>
                </Tooltip>
              </span>
              <span class="hidden lg:inline-flex">
                <Tooltip text="Community and services" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="Community and services"
                    @click="isServiceDialogOpen = true"
                  >
                    Services
                  </Button>
                </Tooltip>
              </span>
              <span v-if="authStore.isAdmin" class="hidden lg:inline-flex">
                <Tooltip :text="`View release updates. Current version: ${currentVersionLabel || 'Unknown version'}`" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    :root-class="hasNewVersion
                      ? '!border-amber-400/70 !bg-amber-50 !text-amber-800 hover:!border-amber-500 hover:!bg-amber-100 hover:!text-amber-900 dark:!border-amber-500/60 dark:!bg-amber-950/35 dark:!text-amber-300 dark:hover:!border-amber-400 dark:hover:!bg-amber-950/55 dark:hover:!text-amber-200'
                      : ''"
                    aria-label="View release updates"
                    @click="openUpdateDialog"
                  >
                    {{ currentVersionLabel || 'Version' }}
                  </Button>
                </Tooltip>
              </span>
              <span v-if="mobileHeaderMenuItems.length" class="inline-flex lg:hidden">
                <ActionMenu
                  label="More"
                  :items="mobileHeaderMenuItems"
                  size="sm"
                  placement="bottom"
                  align="right"
                  trigger-class="shell-header-more"
                  content-class="min-w-36"
                  @select="handleHeaderMenuSelect"
                />
              </span>
            </div>
          </div>
        </header>

        <div
          class="relative min-w-0 overflow-x-hidden bg-card"
          :class="[
            isWorkspacePage ? 'flex min-h-0 flex-1 flex-col overflow-hidden' : '',
            isContainedManagementPage ? 'lg:flex lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-hidden' : '',
            isImmersivePage ? 'p-0' : 'px-4 py-6 sm:px-6',
          ]"
        >
          <RouterView v-slot="{ Component, route: currentRoute }">
            <Suspense :timeout="120">
              <template #default>
                <div
                  class="route-view-content"
                  :class="[
                    isWorkspacePage ? 'flex min-h-0 flex-1 flex-col' : '',
                    isContainedManagementPage ? 'lg:flex lg:min-h-0 lg:flex-1 lg:flex-col' : '',
                    { 'h-full': isImmersivePage },
                  ]"
                >
                  <Transition name="route-view">
                    <KeepAlive :include="cachedRouteNames" :max="cachedRouteMax">
                      <component
                        :is="Component"
                        :key="String(currentRoute.name || currentRoute.path)"
                      />
                    </KeepAlive>
                  </Transition>
                </div>
              </template>
              <template #fallback>
                <PageLoadingState
                  :title="routePendingText"
                  description="Preparing page content..."
                  compact
                />
              </template>
            </Suspense>
          </RouterView>
        </div>
      </main>
    </div>
    <ConfirmDialog
      :open="confirmDialog.open.value"
      :title="confirmDialog.title.value"
      :message="confirmDialog.message.value"
      :confirm-text="confirmDialog.confirmText.value"
      :cancel-text="confirmDialog.cancelText.value"
      @confirm="confirmDialog.confirm"
      @cancel="confirmDialog.cancel"
    />
    <ModalShell
      :open="isServiceDialogOpen"
      max-width="min(22rem, calc(100vw - 24px))"
      :z-index="100"
      panel-class="w-full p-5"
      close-on-backdrop
      aria-label="Community and services"
      @close="isServiceDialogOpen = false"
    >
      <ModalHeader
        title="Community and services"
        title-class="ui-subsection-title"
        :bordered="false"
        flush
        @close="isServiceDialogOpen = false"
      />

      <div class="mt-4 grid gap-2">
        <a
          v-for="item in headerServiceItems"
          :key="item.key"
          :href="item.href"
          target="_blank"
          rel="noopener noreferrer"
          class="shell-service-link group flex min-w-0 items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-left transition-colors hover:border-[hsl(var(--foreground)_/_0.24)] hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          @click="isServiceDialogOpen = false"
        >
          <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground transition-colors group-hover:text-foreground">
            <Icon :icon="item.icon" class="h-4 w-4" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block text-sm font-medium text-foreground">{{ item.label }}</span>
            <span v-if="item.detail" class="mt-0.5 block text-xs leading-5 text-muted-foreground">{{ item.detail }}</span>
          </span>
          <Icon icon="lucide:external-link" class="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
        </a>
      </div>
    </ModalShell>
    <ModalShell
      :open="isApiInfoOpen"
      :z-index="100"
      panel-class="p-6"
      close-on-backdrop
      @close="isApiInfoOpen = false"
    >
          <ModalHeader
            title="API endpoints"
            subtitle="Choose the endpoint for your client"
            title-class="ui-subsection-title"
            :bordered="false"
            flush
            @close="isApiInfoOpen = false"
          />

          <div class="mt-4 space-y-3 text-sm">
            <div>
              <p class="text-xs text-muted-foreground">Base endpoint</p>
              <div class="mt-1 flex items-start gap-2">
                <ValueSurface
                  tag="p"
                  mono
                  break-mode="all"
                  root-class="min-w-0 flex-1"
                >
                  {{ apiBaseUrl }}
                </ValueSurface>
                <Button
                  size="sm"
                  variant="outline"
                  root-class="shrink-0 text-[11px] text-muted-foreground"
                  @click="copyText(apiBaseUrl)"
                >
                  Copy
                </Button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">SDK endpoint</p>
              <div class="mt-1 flex items-start gap-2">
                <ValueSurface
                  tag="p"
                  mono
                  break-mode="all"
                  root-class="min-w-0 flex-1"
                >
                  {{ apiSdkUrl }}
                </ValueSurface>
                <Button
                  size="sm"
                  variant="outline"
                  root-class="shrink-0 text-[11px] text-muted-foreground"
                  @click="copyText(apiSdkUrl)"
                >
                  Copy
                </Button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Supported models</p>
              <div class="mt-1 space-y-3 rounded-2xl border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                <div>
                  <p class="mb-1 text-[11px] text-muted-foreground">Chat models</p>
                  <div class="flex flex-wrap gap-2 text-foreground">
                    <MetaChip
                      v-for="model in supportedChatModels"
                      :key="`chat-${model}`"
                      size="xs"
                    >
                      {{ model }}
                    </MetaChip>
                  </div>
                </div>
                <div>
                  <p class="mb-1 text-[11px] text-muted-foreground">Image models</p>
                <div class="flex flex-wrap gap-2 text-foreground">
                  <MetaChip
                    v-for="model in supportedImageModels"
                    :key="`image-${model}`"
                    size="xs"
                  >
                    {{ model }}
                  </MetaChip>
                </div>
                </div>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">Current API key</p>
              <div class="mt-1 flex items-start gap-2">
                <ValueSurface
                  tag="p"
                  mono
                  break-mode="all"
                  root-class="min-w-0 flex-1"
                >
                  {{ apiKeyDisplay }}
                </ValueSurface>
                <Button
                  size="sm"
                  variant="outline"
                  root-class="shrink-0 text-[11px] text-muted-foreground"
                  :disabled="!currentAuthToken"
                  @click="copyText(apiKeyDisplay)"
                >
                  Copy
                </Button>
              </div>
              <p class="mt-1 text-[11px] text-muted-foreground">
                Use the Authorization: Bearer &lt;current API key&gt; request header.
              </p>
            </div>
          </div>

          <ModalFooter class="mt-6" :bordered="false" flush>
            <Button
              size="xs"
              variant="primary"
              root-class="min-w-14 justify-center"
              @click="isApiInfoOpen = false"
            >
              Done
            </Button>
          </ModalFooter>
    </ModalShell>
    <ModalShell
      :open="isUpdateDialogOpen"
      :z-index="100"
      panel-class="flex min-h-0 max-h-[80dvh] flex-col overflow-hidden p-6"
      close-on-backdrop
      @close="closeUpdateDialog"
    >
      <ModalHeader
        title="Version updates"
        subtitle="View the current version and release notes"
        title-class="ui-subsection-title"
        :bordered="false"
        flush
        @close="closeUpdateDialog"
      />

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <div class="rounded-2xl border border-border bg-background px-4 py-3">
          <p class="text-xs text-muted-foreground">Current version</p>
          <p class="mt-1 text-base font-semibold text-foreground">{{ currentVersionLabel }}</p>
        </div>
        <div class="rounded-2xl border border-border bg-background px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <p class="text-xs text-muted-foreground">Latest version</p>
            <button
              type="button"
              class="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="isCheckingUpdate"
              @click="checkForUpdates(true)"
            >
              {{ isCheckingUpdate ? 'Checking...' : 'Check for updates' }}
            </button>
          </div>
          <p
            class="mt-1 text-base font-semibold"
            :class="hasNewVersion ? 'text-amber-800 dark:text-amber-300' : 'text-foreground'"
          >
            {{ latestVersionLabel }}
          </p>
        </div>
      </div>

      <div
        v-if="updateCheckMessage"
        class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-2xl border px-4 py-3 text-sm"
        :class="updateCheckMessageClass"
      >
        <span class="min-w-0 flex-1 font-medium">{{ updateCheckMessage }}</span>
        <MetaChip
          size="xs"
          :tone="updateCheckBadgeTone"
          strong
          chip-class="shrink-0"
        >
          {{ updateCheckBadgeText }}
        </MetaChip>
      </div>

      <div class="scrollbar-slim mt-5 min-h-0 flex-1 space-y-5 overflow-y-auto pr-2">
        <div
          v-for="release in releaseEntries"
          :key="`${release.version}-${release.date}`"
          class="border-l border-border pl-4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm font-semibold text-foreground">
              {{ release.version === 'Unreleased' ? 'Unreleased' : release.version }}
            </span>
            <span v-if="release.date" class="text-xs text-muted-foreground">{{ release.date }}</span>
            <MetaChip
              v-if="normalizeVersionTag(release.version) === latestVersionLabel"
              size="xs"
              tone="success"
              strong
            >
              Latest
            </MetaChip>
            <MetaChip
              v-if="normalizeVersionTag(release.version) === currentVersionLabel"
              size="xs"
              tone="muted"
            >
              Current
            </MetaChip>
          </div>
          <div class="mt-2 space-y-1.5">
            <div
              v-for="(item, index) in release.items"
              :key="`${release.version}-${index}`"
              class="flex items-start gap-2 text-sm leading-6 text-muted-foreground"
            >
              <MetaChip
                size="xs"
                :tone="releaseItemTone(item.type)"
                strong
                chip-class="mt-0.5 shrink-0"
              >
                {{ releaseItemLabel(item.type) }}
              </MetaChip>
              <span class="min-w-0 flex-1 text-foreground/85">
                <template
                  v-for="(segment, segmentIndex) in splitReleaseInlineCode(item.content)"
                  :key="`${release.version}-${index}-${segmentIndex}`"
                >
                  <code
                    v-if="segment.kind === 'code'"
                    class="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em] text-foreground"
                  >{{ segment.content }}</code>
                  <span v-else>{{ segment.content }}</span>
                </template>
              </span>
            </div>
          </div>
        </div>
        <div v-if="!releaseEntries.length" class="rounded-2xl border border-dashed border-border bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
          No release notes available.
        </div>
      </div>

      <ModalFooter class="mt-6" :bordered="false" flush>
        <Button
          size="xs"
          variant="outline"
          @click="openReleasePage"
        >
          Open releases page
        </Button>
        <Button
          size="xs"
          variant="primary"
          root-class="min-w-14 justify-center"
          @click="closeUpdateDialog"
        >
          Done
        </Button>
        <Button
          v-if="canStartUpdate"
          size="xs"
          variant="primary"
          :disabled="updateProgressState.busy || isUpdateConfirming"
          @click="startUpdate"
        >
          {{ isUpdateConfirming ? 'Waiting for confirmation' : 'Update now' }}
        </Button>
      </ModalFooter>
    </ModalShell>

    <OperationProgressDrawer
      v-if="updateProgressState.open"
      :open="updateProgressState.open"
      :title="updateProgressState.title"
      :subtitle="updateProgressState.subtitle"
      :total="updateProgressState.total"
      :current="updateProgressState.current"
      :status-label="updateProgressState.statusLabel"
      :error="updateProgressState.error"
      :busy="updateProgressState.busy"
      :close-disabled="updateProgressState.busy"
      :tone="updateProgressState.tone"
      :events="updateProgressState.events"
      :summary-items="updateProgressSummary"
      @close="closeUpdateProgress"
    />
  </div>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import {
  PUBLIC_SETTINGS_CHANGED_EVENT,
} from '@/api/settings'
import { versionApi } from '@/api/version'
import { getAuthToken } from '@/api/client'
import type { AuthCapability } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useModelCatalog } from '@/composables/useModelCatalog'
import { usePublicRuntimeConfig } from '@/composables/usePublicRuntimeConfig'
import { useListLayoutPreference } from '@/composables/useListLayoutPreference'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import { ActionMenu, Button, Tooltip, ValueSurface, type ActionMenuItem } from 'nanocat-ui'
import ConfirmDialog from '@/components/ui/AppConfirmDialog.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import OperationProgressDrawer from '@/components/ai/OperationProgressDrawer.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import {
  getBooleanPreference,
  getStringPreference,
  preferenceKeys,
  removePreference,
  setBooleanPreference,
  setStringPreference,
} from '@/lib/preferences'
import { writeClipboardText } from '@/lib/clipboard'
import { focusFirstWithin, focusRefTarget, trapFocusWithin } from '@/lib/focusLoop'
import { applyThemeMode, getStoredThemeMode, setStoredThemeMode, type ThemeMode } from '@/lib/theme'
import {
  normalizeVersionTag,
  parseChangelog,
  splitReleaseInlineCode,
  type ReleaseInfo,
} from '@/lib/release'
import type { UpdateTaskResponse, VersionCheckResponse } from '@/types/api'
import localVersion from '../../../VERSION?raw'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const toast = useToast()
const isSidebarOpen = ref(false)
const isSidebarCollapsed = ref(false)
const isMobileViewport = ref(typeof window !== 'undefined'
  ? !window.matchMedia('(min-width: 1024px)').matches
  : false)
const sidebarToggleRef = ref<ComponentPublicInstance | null>(null)
const sidebarRef = ref<HTMLElement | null>(null)
const confirmDialog = useConfirmDialog()
const isApiInfoOpen = ref(false)
const isServiceDialogOpen = ref(false)
const isUpdateDialogOpen = ref(false)
const isCheckingUpdate = ref(false)
const isUpdateConfirming = ref(false)
const currentVersionTag = ref(normalizeVersionTag(localVersion))
const updateStatus = ref<VersionCheckResponse | null>(null)
const updateRequestError = ref('')
const updateTargetTag = ref('')
const updateProgressRuntime = useOperationProgressRuntime()
const updateProgressState = updateProgressRuntime.state
const releaseEntries = ref<ReleaseInfo[]>([])
const currentAuthToken = ref('')
const themeMode = ref<ThemeMode>(getStoredThemeMode())
type RouteProgressPhase = 'idle' | 'running' | 'finishing'
const pendingNavigationPath = ref('')
const routeProgressPhase = ref<RouteProgressPhase>('idle')
const cachedRouteNames = ['Dashboard', 'Studio', 'Accounts', 'Logs', 'Monitor', 'Gallery', 'Proxy', 'Settings']
const cachedRouteMax = cachedRouteNames.length
const themeOptions: { label: string; value: ThemeMode }[] = [
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
  { label: 'System', value: 'system' },
]
const {
  chatModels: supportedChatModels,
  imageModels: supportedImageModels,
  loadModelCatalog,
} = useModelCatalog()
const {
  apiBaseUrl,
  thirdPartyApps,
  loadPublicRuntimeConfig,
} = usePublicRuntimeConfig()

type NavigationItem = {
  path: string
  label: string
  icon: string
  capability: AuthCapability
}

const menuItems: NavigationItem[] = [
  {
    path: '/',
    label: 'Dashboard',
    icon: 'M4 4h7v7H4V4zm9 0h7v4h-7V4zm0 6h7v10h-7V10zM4 13h7v7H4v-7z',
    capability: 'admin_console',
  },
  {
    path: '/monitor',
    label: 'Monitor',
    icon: 'M4 5h3v14H4V5zm5 6h3v8H9v-8zm5-4h3v12h-3V7zm5 7h3v5h-3v-5z',
    capability: 'admin_console',
  },
  {
    path: '/studio',
    label: 'Chat Studio',
    icon: 'M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-5l-4 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm1 3v6h12V7H6zm2 2 2.1 2.8 2.4-3.1L17 14H7l1-5z',
    capability: 'studio',
  },
  {
    path: '/accounts',
    label: 'Accounts',
    icon: 'M12 12a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 12zm0 2c-4.1 0-7.5 2.2-7.5 5v1h15v-1c0-2.8-3.4-5-7.5-5z',
    capability: 'admin_console',
  },
  {
    path: '/logs',
    label: 'Logs',
    icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z',
    capability: 'admin_console',
  },
  {
    path: '/gallery',
    label: 'Gallery',
    icon: 'M22 16V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2zm-11-4 2.03 2.71L16 11l4 5H8l3-3zM2 6v14a2 2 0 0 0 2 2h14v-2H4V6H2z',
    capability: 'admin_console',
  },
  {
    path: '/proxy',
    label: 'Proxies',
    icon: 'M12 3a5 5 0 0 1 5 5v2h1a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3h1V8a5 5 0 0 1 5-5zm-3 7h6V8a3 3 0 0 0-6 0v2zm-3 2a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1H6z',
    capability: 'admin_console',
  },
  {
    path: '/settings',
    label: 'Settings',
    icon: 'M4 6h10v2H4V6zm12 0h4v2h-4V6zM4 11h6v2H4v-2zm8 0h8v2h-8v-2zM4 16h10v2H4v-2zm12 0h4v2h-4v-2z',
    capability: 'admin_console',
  },
]

const routeTitleMap: Record<string, string> = {
  dashboard: 'Dashboard',
  accounts: 'Accounts',
  logs: 'Logs',
  gallery: 'Gallery',
  proxy: 'Proxies',
  settings: 'Settings',
  monitor: 'Monitor',
  studio: 'Chat Studio',
}

const visibleMenuItems = computed(() => {
  return menuItems.filter(item => authStore.hasCapability(item.capability))
})

const currentPageTitle = computed(() => {
  const routeName = String(route.name || '')
  const item = visibleMenuItems.value.find(item => isNavActive(item.path))
  return item?.label || routeTitleMap[routeName] || 'Dashboard'
})

const isImmersivePage = computed(() => Boolean(route.meta.immersive))
const isWorkspacePage = computed(() => Boolean(route.meta.workspace))
const isManagementPage = computed(() => Boolean(route.meta.management))
const { isWorkspaceLayout } = useListLayoutPreference()
const isContainedManagementPage = computed(() => isManagementPage.value && isWorkspaceLayout.value)
const usesViewportLayout = computed(() => isWorkspacePage.value || isContainedManagementPage.value)
const isMobileSidebarActive = computed(() => isMobileViewport.value && isSidebarOpen.value)
const isSidebarRail = computed(() => (
  !isMobileViewport.value && (isSidebarCollapsed.value || isImmersivePage.value)
))
const sidebarStyle = computed(() => ({
  '--sidebar-width': isSidebarRail.value ? '4rem' : '16rem',
}))

const navItemBaseClass = 'justify-start gap-0 px-1.5'
const activeNavPathSet = computed(() => {
  const name = String(route.name || '')
  const currentPath = route.path
  return new Set(
    visibleMenuItems.value
      .filter((item) => isRoutePathActive(item.path, name, currentPath))
      .map((item) => item.path),
  )
})

function isRoutePathActive(path: string, name: string, currentPath: string) {
  const normalized = path.replace(/^\/+/, '')
  if (!normalized) return name === 'dashboard' || currentPath === '/'
  return currentPath === path || name === normalized
}

const isNavActive = (path: string) => {
  return activeNavPathSet.value.has(path)
}

function isNavPending(path: string) {
  return Boolean(pendingNavigationPath.value)
    && normalizedRoutePath(path) === pendingNavigationPath.value
}

function isNavVisuallyActive(path: string) {
  if (pendingNavigationPath.value) return isNavPending(path)
  return isNavActive(path)
}

function buildNavItemClass(path: string) {
  const base = navItemBaseClass
  if (isNavVisuallyActive(path)) {
    return `${base} rounded-[0.9rem] border-[hsl(var(--primary)_/_0.28)] bg-[hsl(var(--primary)_/_0.08)] font-semibold text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)_/_0.08)]`
  }
  return `${base} rounded-[0.9rem] border-transparent text-muted-foreground hover:border-border hover:bg-[hsl(var(--secondary)_/_0.55)] hover:text-foreground`
}

function buildNavIconClass(path: string) {
  if (isNavVisuallyActive(path)) {
    return 'border-[hsl(var(--primary)_/_0.28)] bg-[hsl(var(--card))] text-foreground shadow-sm'
  }
  return 'border-border bg-[hsl(var(--card))] text-muted-foreground group-hover:border-[hsl(var(--foreground)_/_0.28)] group-hover:text-foreground'
}

const navItemClassMap = computed<Record<string, string>>(() => {
  const entries = visibleMenuItems.value.map((item) => [item.path, buildNavItemClass(item.path)])
  return Object.fromEntries(entries)
})

const navIconClassMap = computed<Record<string, string>>(() => {
  const entries = visibleMenuItems.value.map((item) => [item.path, buildNavIconClass(item.path)])
  return Object.fromEntries(entries)
})


const apiSdkUrl = computed(() => `${apiBaseUrl.value}/v1`)
const apiKeyDisplay = computed(() => currentAuthToken.value || 'Not logged in')
const currentVersionLabel = computed(() => normalizeVersionTag(
  updateStatus.value?.current_tag || currentVersionTag.value || '',
))
const latestVersionLabel = computed(() => normalizeVersionTag(
  updateStatus.value?.latest_tag || currentVersionTag.value || '',
))
const hasNewVersion = computed(() => updateStatus.value?.update_available === true)
const canStartUpdate = computed(() => updateStatus.value?.can_update === true && !updateProgressState.busy)
const updateProgressSummary = computed(() => [
  {
    key: 'current-version',
    label: 'Current version',
    value: currentVersionLabel.value || 'Unknown',
  },
  {
    key: 'target-version',
    label: 'Target version',
    value: updateTargetTag.value || latestVersionLabel.value || 'Unknown',
  },
])
const updateCheckMessage = computed(() => {
  if (isCheckingUpdate.value) return updateCheckingMessage
  return updateRequestError.value || updateStatus.value?.status_message || ''
})
const updateCheckMessageClass = computed(() => {
  if (isCheckingUpdate.value) return 'border-cyan-500/35 bg-cyan-500/10 text-cyan-700'
  if (updateRequestError.value || updateStatus.value?.tone === 'warning') return 'border-amber-500/40 bg-amber-500/10 text-amber-700'
  if (updateStatus.value?.tone === 'success') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700'
  return 'border-border bg-muted/40 text-muted-foreground'
})
const updateCheckBadgeText = computed(() => {
  if (isCheckingUpdate.value) return 'Checking'
  if (updateRequestError.value) return 'Request failed'
  return updateStatus.value?.status_label || 'Not checked'
})
const updateCheckBadgeTone = computed(() => {
  if (isCheckingUpdate.value) return 'info'
  if (updateRequestError.value || updateStatus.value?.tone === 'warning') return 'warning'
  if (updateStatus.value?.tone === 'success') return 'success'
  return 'muted'
})
function releaseItemTone(type: string): 'default' | 'muted' | 'success' | 'warning' | 'danger' | 'info' {
  const value = String(type || '').trim()
  if (['新增', '添加', 'Added'].includes(value)) return 'success'
  if (['优化', '改进', 'Changed', 'Improved'].includes(value)) return 'info'
  if (['修复', '修正', 'Fixed'].includes(value)) return 'warning'
  if (['移除', '删除', '废弃', 'Removed', 'Deprecated'].includes(value)) return 'danger'
  return 'muted'
}
function releaseItemLabel(type: string) {
  const value = String(type || '').trim()
  const labels: Record<string, string> = {
    新增: 'Added',
    添加: 'Added',
    优化: 'Improved',
    改进: 'Improved',
    修复: 'Fixed',
    修正: 'Fixed',
    移除: 'Removed',
    删除: 'Removed',
    废弃: 'Deprecated',
  }
  return labels[value] || value
}
const canvasHref = computed(() => {
  const canvas = thirdPartyApps.value?.infinite_canvas
  const token = getAuthToken()
  if (!canvas?.enabled || !canvas.url.trim() || !token) return ''
  return buildThirdPartyHref(canvas.url, apiBaseUrl.value, token)
})
const themeButtonText = computed(() => themeOptions.find(option => option.value === themeMode.value)?.label || 'System')
const themeButtonTitle = computed(() => `Current theme: ${themeButtonText.value}. Click to switch.`)
type HeaderServiceItem = {
  key: string
  label: string
  detail?: string
  href: string
  icon: string
}

const headerServiceItems: HeaderServiceItem[] = [
  {
    key: 'service-qq',
    label: 'QQ community group: 1005859624',
    href: 'https://qm.qq.com/q/yegwCqJisS',
    icon: 'lucide:messages-square',
  },
  {
    key: 'service-account',
    label: 'Buy image-generation accounts',
    href: 'https://pay.ldxp.cn/shop/yukkcat',
    icon: 'lucide:shopping-bag',
  },
  {
    key: 'service-api',
    label: 'Image generation API',
    detail: 'Low volume ¥0.02/image · Relay ¥0.01/image · High volume / enterprise ¥0.009/image',
    href: 'https://api.klong.lat',
    icon: 'lucide:badge-dollar-sign',
  },
]

const mobileHeaderMenuItems = computed<ActionMenuItem[]>(() => {
  const items: ActionMenuItem[] = []
  if (canvasHref.value) items.push({ key: 'canvas', label: 'Infinite canvas' })
  if (authStore.isAdmin) {
    items.push(
      { key: 'api-info', label: 'API information' },
      { key: 'updates', label: 'Version updates' },
    )
  }
  items.push({ key: 'services', label: 'Community and services', dividerBefore: items.length > 0 })
  return items
})
const routePendingText = computed(() => `Loading ${currentPageTitle.value}`)
let systemThemeMedia: MediaQueryList | null = null
let viewportMedia: MediaQueryList | null = null
const prefetchedRoutePaths = new Set<string>()
const routeProgressDelayMs = 140
const routeProgressFinishMs = 140
let routeProgressDelayTimer: number | null = null
let routeProgressFinishTimer: number | null = null
const defaultReleasePageUrl = 'https://github.com/yukkcat/chatgpt2api/releases'
const releasePageUrl = computed(() => updateStatus.value?.release_url || defaultReleasePageUrl)
const updateCheckingMessage = 'Checking for the latest version...'
const updateTaskPollIntervalMs = 1000
let updateTaskPollTimer: number | null = null
let updateReloadScheduled = false
const routeViewLoaders: Record<string, () => Promise<unknown>> = {
  '/': () => import('@/views/Dashboard.vue'),
  '/accounts': () => import('@/views/Accounts.vue'),
  '/logs': () => import('@/views/Logs.vue'),
  '/gallery': () => import('@/views/Gallery.vue'),
  '/monitor': () => import('@/views/Monitor.vue'),
  '/proxy': () => import('@/views/Proxy.vue'),
  '/settings': () => import('@/views/Settings.vue'),
  '/studio': () => import('@/views/Studio.vue'),
}

function setMobileSidebarScrollLock(locked: boolean) {
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('app-mobile-sidebar-open', locked)
  document.body.classList.toggle('app-mobile-sidebar-open', locked)
}

function focusSidebarToggle() {
  void nextTick(() => {
    if (!isMobileViewport.value) return
    focusRefTarget(sidebarToggleRef.value)
  })
}

function focusSidebarNavigation() {
  void nextTick(() => {
    if (!isMobileViewport.value || !isSidebarOpen.value) return
    focusFirstWithin(sidebarRef.value, '#app-sidebar-navigation a[href]')
  })
}

function handleSidebarKeydown(event: KeyboardEvent) {
  if (!isMobileSidebarActive.value) return
  trapFocusWithin(sidebarRef.value, event)
}

function openSidebar() {
  if (!isMobileViewport.value) return
  isSidebarOpen.value = true
  focusSidebarNavigation()
}

function closeSidebar(options: { restoreFocus?: boolean } = {}) {
  const wasOpen = isSidebarOpen.value
  isSidebarOpen.value = false
  if (wasOpen && options.restoreFocus !== false) focusSidebarToggle()
}

function handleViewportChange(event: MediaQueryListEvent) {
  isMobileViewport.value = !event.matches
  if (event.matches) closeSidebar({ restoreFocus: false })
}

function setupViewportListener() {
  if (typeof window === 'undefined') return
  viewportMedia = window.matchMedia('(min-width: 1024px)')
  isMobileViewport.value = !viewportMedia.matches
  viewportMedia.addEventListener('change', handleViewportChange)
}

function teardownViewportListener() {
  viewportMedia?.removeEventListener('change', handleViewportChange)
  viewportMedia = null
  setMobileSidebarScrollLock(false)
}

function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !isMobileViewport.value || !isSidebarOpen.value) return
  event.preventDefault()
  closeSidebar()
}

watch([isMobileViewport, isSidebarOpen], ([isMobile, isOpen]) => {
  setMobileSidebarScrollLock(isMobile && isOpen)
})

watch(
  () => route.path,
  () => {
    closeSidebar()
    void loadPublicRuntimeConfig()
  }
)

isSidebarCollapsed.value = getBooleanPreference(preferenceKeys.sidebarCollapsed, false)

watch(isSidebarCollapsed, (value) => {
  setBooleanPreference(preferenceKeys.sidebarCollapsed, value)
})

function buildThirdPartyHref(appUrl: string, baseUrl: string, apiKey: string) {
  const url = appUrl.trim()
  try {
    const target = new URL(url)
    target.searchParams.set('apiKey', apiKey)
    target.searchParams.set('baseUrl', baseUrl)
    return target.toString()
  } catch {
    return `${url}${url.includes('?') ? '&' : '?'}apiKey=${encodeURIComponent(apiKey)}&baseUrl=${encodeURIComponent(baseUrl)}`
  }
}

function refreshPage() {
  window.location.reload()
}

async function handleLogout() {
  closeSidebar()
  await authStore.logout()
  await router.replace({ name: 'login' })
}

async function openApiInfo() {
  currentAuthToken.value = getAuthToken()
  isApiInfoOpen.value = true
  await Promise.all([loadModelCatalog(), loadPublicRuntimeConfig()])
}

async function copyText(value: string) {
  const text = String(value || '').trim()
  if (!text) return
  try {
    await writeClipboardText(text)
    toast.success('Copied')
  } catch (error) {
    console.error('Copy failed', error)
    toast.error('Copy failed. Please copy it manually.')
  }
}

async function openInfiniteCanvas() {
  if (!canvasHref.value) return
  const ok = await confirmDialog.ask({
    title: 'Open infinite canvas',
    message: 'This will open an external canvas and include the current API endpoint and API key. Continue?',
    confirmText: 'Open',
    cancelText: 'Cancel',
  })
  if (ok) {
    window.open(canvasHref.value, '_blank', 'noopener,noreferrer')
  }
}

function handleHeaderMenuSelect(key: string) {
  if (key === 'services') {
    isServiceDialogOpen.value = true
    return
  }
  if (key === 'canvas') {
    void openInfiniteCanvas()
    return
  }
  if (key === 'updates') {
    openUpdateDialog()
    return
  }
  if (key === 'api-info') {
    void openApiInfo()
  }
}

function setThemeMode(mode: ThemeMode) {
  themeMode.value = mode
  setStoredThemeMode(mode)
}

function cycleThemeMode() {
  const index = themeOptions.findIndex(option => option.value === themeMode.value)
  const next = themeOptions[(index + 1) % themeOptions.length]
  setThemeMode(next.value)
}

function openUpdateDialog() {
  isUpdateDialogOpen.value = true
}

function openReleasePage() {
  window.open(releasePageUrl.value, '_blank', 'noopener,noreferrer')
  closeUpdateDialog()
}

function closeUpdateDialog() {
  const latestTag = updateStatus.value?.latest_tag || ''
  if (updateStatus.value?.update_available && latestTag) {
    setStringPreference(preferenceKeys.updateDismissedTag, latestTag)
  }
  isUpdateDialogOpen.value = false
}

function clearUpdateTaskPollTimer() {
  if (updateTaskPollTimer === null) return
  window.clearTimeout(updateTaskPollTimer)
  updateTaskPollTimer = null
}

function applyUpdateTask(task: UpdateTaskResponse, open: boolean) {
  if (task.state === 'idle') return
  updateTargetTag.value = normalizeVersionTag(task.latest_tag || updateTargetTag.value)
  currentVersionTag.value = normalizeVersionTag(task.current_tag || currentVersionTag.value)
  updateProgressState.open = open
  updateProgressState.title = task.busy ? 'Updating ChatGPT2API' : 'ChatGPT2API update'
  updateProgressState.subtitle = task.latest_tag ? `Target version ${normalizeVersionTag(task.latest_tag)}` : ''
  updateProgressState.total = task.total
  updateProgressState.current = task.current
  updateProgressState.statusLabel = task.status_label
  updateProgressState.message = task.message
  updateProgressState.error = task.error
  updateProgressState.busy = task.busy
  updateProgressState.tone = task.tone
  updateProgressState.events = task.events.map(event => ({
    key: event.id,
    timestamp: event.timestamp,
    label: event.label,
    message: event.message,
    tone: event.tone,
  }))
}

function scheduleUpdateTaskPoll() {
  clearUpdateTaskPollTimer()
  updateTaskPollTimer = window.setTimeout(() => {
    void pollUpdateTask()
  }, updateTaskPollIntervalMs)
}

async function startUpdate() {
  if (isUpdateConfirming.value || !canStartUpdate.value) return
  const targetTag = normalizeVersionTag(updateStatus.value?.latest_tag || '')
  if (!targetTag) return

  isUpdateConfirming.value = true
  let confirmed = false
  try {
    confirmed = await confirmDialog.ask({
      title: 'Confirm update',
      message: `Version ${targetTag} is available. The current version is ${currentVersionLabel.value || 'unknown'}. Confirm to download and install the update. The service will restart automatically, usually within 30 seconds to 2 minutes.`,
      confirmText: 'Update now',
      cancelText: 'Cancel',
    })
  } finally {
    isUpdateConfirming.value = false
  }
  if (!confirmed) return

  clearUpdateTaskPollTimer()
  updateTargetTag.value = targetTag
  isUpdateDialogOpen.value = false

  try {
    const task = await versionApi.startUpdate()
    setStringPreference(preferenceKeys.updateActiveTaskId, task.task_id)
    applyUpdateTask(task, true)
    if (task.busy) scheduleUpdateTaskPoll()
    else await checkForUpdates(false)
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Online update failed. Please try again later.'
    toast.error(message)
  }
}

async function pollUpdateTask() {
  try {
    const task = await versionApi.updateTask()
    const activeTaskId = getStringPreference(preferenceKeys.updateActiveTaskId)
    const shouldOpen = task.busy || Boolean(task.task_id && task.task_id === activeTaskId)
    applyUpdateTask(task, shouldOpen)
    if (task.busy) {
      scheduleUpdateTaskPoll()
      return
    }
    clearUpdateTaskPollTimer()
    await checkForUpdates(false)
    const targetTag = normalizeVersionTag(task.latest_tag)
    if (
      !updateReloadScheduled
      && task.state === 'succeeded'
      && targetTag
      && normalizeVersionTag(localVersion) !== targetTag
    ) {
      updateReloadScheduled = true
      window.setTimeout(() => window.location.reload(), 400)
    }
  } catch {
    if (updateProgressState.busy) scheduleUpdateTaskPoll()
  }
}

function closeUpdateProgress() {
  if (!updateProgressRuntime.close()) return
  clearUpdateTaskPollTimer()
  removePreference(preferenceKeys.updateActiveTaskId)
}

async function checkForUpdates(showMessage = true, openAvailable = false) {
  if (isCheckingUpdate.value) return
  isCheckingUpdate.value = true
  updateRequestError.value = ''
  try {
    const result = await versionApi.check(showMessage)
    updateStatus.value = result
    currentVersionTag.value = result.current_tag
    releaseEntries.value = parseChangelog(result.changelog)
    if (
      openAvailable
      && result.update_available
      && getStringPreference(preferenceKeys.updateDismissedTag) !== result.latest_tag
    ) {
      isUpdateDialogOpen.value = true
    }
    if (showMessage) {
      if (result.tone === 'warning') toast.warning(result.status_message)
      else if (result.update_available) toast.info(result.status_message)
      else toast.success(result.status_message)
    }
  } catch {
    updateRequestError.value = 'Could not connect to the backend to check for updates. Please try again later.'
    if (showMessage) toast.warning(updateRequestError.value)
  } finally {
    isCheckingUpdate.value = false
  }
}

async function loadCurrentVersion() {
  try {
    const result = await versionApi.current()
    const runtimeVersion = String(result.tag || '').trim()
    if (runtimeVersion) currentVersionTag.value = runtimeVersion
  } catch {}
}

function handleSystemThemeChange() {
  if (themeMode.value === 'system') {
    applyThemeMode(themeMode.value)
  }
}

function setupSystemThemeListener() {
  if (typeof window === 'undefined') return
  systemThemeMedia = window.matchMedia('(prefers-color-scheme: dark)')
  systemThemeMedia.addEventListener('change', handleSystemThemeChange)
}

function handlePublicSettingsChanged() {
  void loadPublicRuntimeConfig(true)
}

function normalizedRoutePath(path: string) {
  if (!path || path === '/') return '/'
  return `/${path.replace(/^\/+/, '').split(/[?#]/)[0]}`
}

function clearRouteProgressDelayTimer() {
  if (routeProgressDelayTimer === null) return
  window.clearTimeout(routeProgressDelayTimer)
  routeProgressDelayTimer = null
}

function clearRouteProgressFinishTimer() {
  if (routeProgressFinishTimer === null) return
  window.clearTimeout(routeProgressFinishTimer)
  routeProgressFinishTimer = null
}

function beginRouteNavigation(path: string) {
  const normalizedPath = normalizedRoutePath(path)
  if (normalizedPath === normalizedRoutePath(route.path)) return
  if (pendingNavigationPath.value === normalizedPath && routeProgressPhase.value !== 'finishing') return

  pendingNavigationPath.value = normalizedPath
  clearRouteProgressDelayTimer()
  clearRouteProgressFinishTimer()
  routeProgressPhase.value = 'idle'
  routeProgressDelayTimer = window.setTimeout(() => {
    routeProgressDelayTimer = null
    if (pendingNavigationPath.value !== normalizedPath) return
    routeProgressPhase.value = 'running'
  }, routeProgressDelayMs)
}

function finishRouteNavigation(path?: string) {
  const normalizedPath = path ? normalizedRoutePath(path) : ''
  if (
    normalizedPath
    && pendingNavigationPath.value
    && normalizedPath !== pendingNavigationPath.value
  ) return

  pendingNavigationPath.value = ''
  clearRouteProgressDelayTimer()
  clearRouteProgressFinishTimer()
  if (routeProgressPhase.value !== 'running') {
    routeProgressPhase.value = 'idle'
    return
  }

  routeProgressPhase.value = 'finishing'
  routeProgressFinishTimer = window.setTimeout(() => {
    routeProgressFinishTimer = null
    routeProgressPhase.value = 'idle'
  }, routeProgressFinishMs)
}

function prefetchRouteView(path: string) {
  const normalizedPath = normalizedRoutePath(path)
  const loader = routeViewLoaders[normalizedPath]
  if (!loader || prefetchedRoutePaths.has(normalizedPath)) return
  prefetchedRoutePaths.add(normalizedPath)
  void loader().catch(() => {
    prefetchedRoutePaths.delete(normalizedPath)
  })
}

function handleNavClick(path: string) {
  beginRouteNavigation(path)
  closeSidebar()
}

const removeRouteBeforeGuard = router.beforeEach((to, from) => {
  if (to.fullPath !== from.fullPath) beginRouteNavigation(to.path)
})
const removeRouteAfterHook = router.afterEach((to) => {
  void nextTick(() => finishRouteNavigation(to.path))
})
const removeRouteErrorHook = router.onError((_error, to) => {
  finishRouteNavigation(to.path)
})

onMounted(() => {
  applyThemeMode(themeMode.value)
  setupSystemThemeListener()
  setupViewportListener()
  window.addEventListener(PUBLIC_SETTINGS_CHANGED_EVENT, handlePublicSettingsChanged)
  window.addEventListener('keydown', handleWindowKeydown)
  void loadCurrentVersion()
  if (authStore.isAdmin) {
    void checkForUpdates(false, true)
    void pollUpdateTask()
  }
  void loadPublicRuntimeConfig()
})

onBeforeUnmount(() => {
  window.removeEventListener(PUBLIC_SETTINGS_CHANGED_EVENT, handlePublicSettingsChanged)
  window.removeEventListener('keydown', handleWindowKeydown)
  systemThemeMedia?.removeEventListener('change', handleSystemThemeChange)
  systemThemeMedia = null
  teardownViewportListener()
  clearUpdateTaskPollTimer()
  clearRouteProgressDelayTimer()
  clearRouteProgressFinishTimer()
  removeRouteBeforeGuard()
  removeRouteAfterHook()
  removeRouteErrorHook()
})

</script>

<style scoped>
:global(html.app-mobile-sidebar-open),
:global(body.app-mobile-sidebar-open) {
  overflow: hidden;
}

.route-view-content {
  min-width: 0;
}

.route-view-enter-active {
  transition: opacity 140ms ease-out;
}

.route-view-enter-from {
  opacity: 0.88;
}

.route-progress-enter-active,
.route-progress-leave-active {
  transition: opacity 100ms ease-out;
}

.route-progress-enter-from,
.route-progress-leave-to {
  opacity: 0;
}

.shell-route-progress {
  background: hsl(var(--primary) / 0.12);
}

.shell-route-progress-bar {
  transform: scaleX(0.08);
  transform-origin: left center;
  animation: shell-route-progress-running 1.4s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}

.shell-route-progress-bar--finishing {
  animation: none;
  transform: scaleX(1);
  transition: transform 120ms ease-out;
}

@keyframes shell-route-progress-running {
  0% {
    transform: scaleX(0.08);
  }

  60% {
    transform: scaleX(0.62);
  }

  100% {
    transform: scaleX(0.84);
  }
}

.sidebar-nav-scroll {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.sidebar-nav-scroll::-webkit-scrollbar {
  display: none;
}

.sidebar-label {
  display: block;
  min-width: 0;
  max-width: 11rem;
  flex: 1 1 auto;
  overflow: hidden;
  margin-inline-start: 0.75rem;
  white-space: nowrap;
  opacity: 1;
  transform: translateX(0);
  transition:
    max-width 0.2s ease,
    margin-inline-start 0.2s ease,
    opacity 0.12s ease 0.04s,
    transform 0.2s ease;
}

.sidebar-brand-label {
  flex: 0 1 auto;
}

.sidebar-section-label {
  max-height: 1.75rem;
  overflow: hidden;
  padding-bottom: 0.5rem;
  white-space: nowrap;
  opacity: 1;
  transform: translateX(0);
  transition:
    max-height 0.2s ease,
    padding-bottom 0.2s ease,
    opacity 0.12s ease 0.04s,
    transform 0.2s ease;
}

.sidebar-footer-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.sidebar-logout {
  display: inline-flex;
  min-width: 0;
  height: 2rem;
  flex: 1 1 auto;
  justify-content: center;
  overflow: hidden;
  padding-inline: 0.75rem;
}

.sidebar-logout-label {
  flex: 0 1 auto;
  margin-inline-start: 0;
}

.sidebar-footer-tooltip-trigger {
  display: inline-flex;
  width: 2.25rem;
  height: 2.25rem;
  flex: none;
  align-items: center;
  justify-content: center;
}

.sidebar-collapse-button {
  flex: none;
}

.sidebar--rail .sidebar-label {
  max-width: 0;
  margin-inline-start: 0;
  opacity: 0;
  transform: translateX(-4px);
  transition-delay: 0s;
}

.sidebar--rail .sidebar-section-label {
  max-height: 0;
  padding-bottom: 0;
  opacity: 0;
  transform: translateX(-4px);
  transition-delay: 0s;
}

.sidebar--rail .sidebar-footer-actions {
  flex-direction: column;
  gap: 0.5rem;
}

.sidebar--rail .sidebar-logout {
  width: 2.25rem;
  height: 2.25rem;
  flex: 0 0 2.25rem;
  justify-content: center;
  padding: 0;
}

.sidebar--rail .sidebar-collapse-button {
  width: 2.25rem;
  height: 2.25rem;
}

@media (prefers-reduced-motion: reduce) {
  .route-view-enter-active,
  .route-progress-enter-active,
  .route-progress-leave-active,
  .shell-route-progress-bar,
  .shell-route-progress-bar--finishing {
    animation: none;
    transition: none;
  }

  .shell-route-progress-bar {
    transform: scaleX(0.84);
  }

  .shell-route-progress-bar--finishing {
    transform: scaleX(1);
  }

  .sidebar-label,
  .sidebar-section-label {
    transition: none;
  }
}

@media (max-width: 1023px) {
  .sidebar--rail .sidebar-label {
    max-width: 11rem;
    margin-inline-start: 0.75rem;
    opacity: 1;
    transform: translateX(0);
  }

  .sidebar--rail .sidebar-section-label {
    max-height: 1.75rem;
    padding-bottom: 0.5rem;
    opacity: 1;
    transform: translateX(0);
  }

  .sidebar--rail .sidebar-footer-actions {
    flex-direction: row;
    gap: 0.75rem;
  }

  .sidebar--rail .sidebar-logout {
    width: auto;
    height: 2rem;
    flex: 1 1 auto;
    justify-content: center;
    padding-inline: 0.75rem;
  }

  .sidebar-collapse-button {
    display: none;
  }
}
</style>
