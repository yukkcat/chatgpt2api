<template>
  <div class="app-shell min-h-screen">
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
            导航
          </p>
          <div class="space-y-1">
            <RouterLink
              v-for="item in visibleMenuItems"
              :key="item.path"
              :to="item.path"
              class="shell-nav-item group flex items-center overflow-hidden rounded-lg border border-transparent py-1.5 text-sm font-medium transition-colors"
              :class="navItemClassMap[item.path]"
              :aria-label="item.label"
              @mouseenter="prefetchRouteView(item.path)"
              @focus="prefetchRouteView(item.path)"
              @click="handleNavClick"
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
              aria-label="退出登录"
              @click="handleLogout"
            >
              <Tooltip v-if="isSidebarRail" text="退出登录" placement="right">
                <span class="sidebar-footer-tooltip-trigger">
                  <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M10 17l5-5-5-5" />
                    <path d="M15 12H3" />
                    <path d="M21 19V5a2 2 0 0 0-2-2h-6" />
                  </svg>
                </span>
              </Tooltip>
              <span class="sidebar-label sidebar-logout-label">退出登录</span>
            </Button>
            <Button
              v-if="!isImmersivePage"
              size="sm"
              variant="outline"
              icon-only
              root-class="sidebar-collapse-button shell-sidebar-footer-button shrink-0 rounded-full text-muted-foreground"
              @click="isSidebarCollapsed = !isSidebarCollapsed"
              :aria-label="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'"
              :aria-expanded="!isSidebarCollapsed"
              aria-controls="app-sidebar-navigation"
            >
              <Tooltip v-if="isSidebarRail" :text="isSidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" placement="right">
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
              aria-label="打开导航"
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
                <Tooltip text="打开无限画布" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="打开无限画布"
                    @click="openInfiniteCanvas"
                  >
                    画布
                  </Button>
                </Tooltip>
              </span>
              <Tooltip text="刷新当前页面" placement="bottom">
                <Button
                  size="sm"
                  variant="outline"
                  aria-label="刷新当前页面"
                  @click="refreshPage"
                >
                  刷新
                </Button>
              </Tooltip>
            </div>
            <div class="flex items-center gap-[8px]">
              <span v-if="authStore.isAdmin" class="hidden lg:inline-flex">
                <Tooltip text="查看接口信息" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="查看接口信息"
                    @click="openApiInfo"
                  >
                    接口
                  </Button>
                </Tooltip>
              </span>
              <span class="hidden lg:inline-flex">
                <Tooltip text="交流与服务" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="交流与服务"
                    @click="isServiceDialogOpen = true"
                  >
                    服务
                  </Button>
                </Tooltip>
              </span>
              <span v-if="authStore.isAdmin" class="hidden lg:inline-flex">
                <Tooltip :text="`查看版本更新，当前 ${currentVersionLabel || '版本未知'}`" placement="bottom">
                  <Button
                    size="sm"
                    variant="outline"
                    aria-label="查看版本更新"
                    @click="openUpdateDialog"
                  >
                    {{ currentVersionLabel || '版本' }}
                  </Button>
                </Tooltip>
              </span>
              <span v-if="mobileHeaderMenuItems.length" class="inline-flex lg:hidden">
                <ActionMenu
                  label="更多"
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
                  <KeepAlive :include="cachedRouteNames" :max="cachedRouteMax">
                    <component
                      :is="Component"
                      :key="String(currentRoute.name || currentRoute.path)"
                    />
                  </KeepAlive>
                </div>
              </template>
              <template #fallback>
                <PageLoadingState
                  :title="routePendingText"
                  description="正在准备页面内容..."
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
      aria-label="交流与服务"
      @close="isServiceDialogOpen = false"
    >
      <ModalHeader
        title="交流与服务"
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
            title="API 接口"
            subtitle="根据客户端选择对应接口"
            title-class="ui-subsection-title"
            :bordered="false"
            flush
            @close="isApiInfoOpen = false"
          />

          <div class="mt-4 space-y-3 text-sm">
            <div>
              <p class="text-xs text-muted-foreground">基础端点</p>
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
                  复制
                </Button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">SDK 接口</p>
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
                  复制
                </Button>
              </div>
            </div>
            <div>
              <p class="text-xs text-muted-foreground">支持模型</p>
              <div class="mt-1 space-y-3 rounded-2xl border border-border bg-background px-3 py-2 text-xs text-muted-foreground">
                <div>
                  <p class="mb-1 text-[11px] text-muted-foreground">聊天模型</p>
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
                  <p class="mb-1 text-[11px] text-muted-foreground">图片模型</p>
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
              <p class="text-xs text-muted-foreground">当前调用密钥</p>
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
                  复制
                </Button>
              </div>
              <p class="mt-1 text-[11px] text-muted-foreground">
                请求头使用 Authorization: Bearer &lt;当前调用密钥&gt;。
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
              知道了
            </Button>
          </ModalFooter>
    </ModalShell>
    <ModalShell
      :open="isUpdateDialogOpen"
      :z-index="100"
      panel-class="flex max-h-[min(46rem,calc(100dvh-2rem))] flex-col p-6"
      close-on-backdrop
      @close="isUpdateDialogOpen = false"
    >
      <ModalHeader
        title="版本更新"
        subtitle="查看当前版本和更新日志"
        title-class="ui-subsection-title"
        :bordered="false"
        flush
        @close="isUpdateDialogOpen = false"
      />

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <div class="rounded-2xl border border-border bg-background px-4 py-3">
          <p class="text-xs text-muted-foreground">当前版本</p>
          <p class="mt-1 text-base font-semibold text-foreground">{{ currentVersionLabel }}</p>
        </div>
        <div class="rounded-2xl border border-border bg-background px-4 py-3">
          <div class="flex items-center justify-between gap-3">
            <p class="text-xs text-muted-foreground">最新版本</p>
            <button
              type="button"
              class="text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="isCheckingUpdate"
              @click="checkForUpdates(true)"
            >
              {{ isCheckingUpdate ? '检查中...' : '检查更新' }}
            </button>
          </div>
          <p
            class="mt-1 text-base font-semibold"
            :class="hasNewVersion ? 'text-rose-600 dark:text-rose-400' : 'text-foreground'"
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
              {{ release.version === 'Unreleased' ? '未发布' : release.version }}
            </span>
            <span v-if="release.date" class="text-xs text-muted-foreground">{{ release.date }}</span>
            <MetaChip
              v-if="normalizeVersionTag(release.version) === latestVersionLabel"
              size="xs"
              tone="success"
              strong
            >
              最新
            </MetaChip>
            <MetaChip
              v-if="normalizeVersionTag(release.version) === currentVersionLabel"
              size="xs"
              tone="muted"
            >
              当前
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
                {{ item.type }}
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
          暂无更新日志。
        </div>
      </div>

      <ModalFooter class="mt-6" :bordered="false" flush>
        <Button
          size="xs"
          variant="outline"
          @click="openReleasePage"
        >
          打开发布页
        </Button>
        <Button
          size="xs"
          variant="primary"
          root-class="min-w-14 justify-center"
          @click="isUpdateDialogOpen = false"
        >
          知道了
        </Button>
      </ModalFooter>
    </ModalShell>
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
import { ActionMenu, Button, Tooltip, ValueSurface, type ActionMenuItem } from 'nanocat-ui'
import ConfirmDialog from '@/components/ui/AppConfirmDialog.vue'
import MetaChip from '@/components/ai/MetaChip.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useToast } from '@/composables/useToast'
import { getBooleanPreference, preferenceKeys, setBooleanPreference } from '@/lib/preferences'
import { writeClipboardText } from '@/lib/clipboard'
import { focusFirstWithin, focusRefTarget, trapFocusWithin } from '@/lib/focusLoop'
import { applyThemeMode, getStoredThemeMode, setStoredThemeMode, type ThemeMode } from '@/lib/theme'
import {
  isNewerVersion,
  latestReleasedVersion,
  normalizeVersionTag,
  parseChangelog,
  splitReleaseInlineCode,
  type ReleaseInfo,
} from '@/lib/release'
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
const currentVersionTag = ref(normalizeVersionTag(localVersion))
const latestVersionTag = ref('')
const releaseEntries = ref<ReleaseInfo[]>([])
const releaseEntriesSource = ref<'none' | 'local' | 'remote'>('none')
const updateCheckMessage = ref('')
const updateCheckStatus = ref<'idle' | 'checking' | 'available' | 'current' | 'warning'>('idle')
const currentAuthToken = ref('')
const themeMode = ref<ThemeMode>(getStoredThemeMode())
const cachedRouteNames = ['Dashboard', 'Studio', 'Accounts', 'Logs', 'Monitor', 'Gallery', 'Proxy', 'Settings']
const cachedRouteMax = cachedRouteNames.length
const themeOptions: { label: string; value: ThemeMode }[] = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
  { label: '系统', value: 'system' },
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
    label: '概览中心',
    icon: 'M4 4h7v7H4V4zm9 0h7v4h-7V4zm0 6h7v10h-7V10zM4 13h7v7H4v-7z',
    capability: 'admin_console',
  },
  {
    path: '/monitor',
    label: '实时监控',
    icon: 'M4 5h3v14H4V5zm5 6h3v8H9v-8zm5-4h3v12h-3V7zm5 7h3v5h-3v-5z',
    capability: 'admin_console',
  },
  {
    path: '/studio',
    label: '对话画图',
    icon: 'M5 4h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-5l-4 4v-4H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm1 3v6h12V7H6zm2 2 2.1 2.8 2.4-3.1L17 14H7l1-5z',
    capability: 'studio',
  },
  {
    path: '/accounts',
    label: '账号管理',
    icon: 'M12 12a3.5 3.5 0 1 0-3.5-3.5A3.5 3.5 0 0 0 12 12zm0 2c-4.1 0-7.5 2.2-7.5 5v1h15v-1c0-2.8-3.4-5-7.5-5z',
    capability: 'admin_console',
  },
  {
    path: '/logs',
    label: '日志管理',
    icon: 'M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z',
    capability: 'admin_console',
  },
  {
    path: '/gallery',
    label: '图片管理',
    icon: 'M22 16V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2zm-11-4 2.03 2.71L16 11l4 5H8l3-3zM2 6v14a2 2 0 0 0 2 2h14v-2H4V6H2z',
    capability: 'admin_console',
  },
  {
    path: '/proxy',
    label: '代理管理',
    icon: 'M12 3a5 5 0 0 1 5 5v2h1a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3h1V8a5 5 0 0 1 5-5zm-3 7h6V8a3 3 0 0 0-6 0v2zm-3 2a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5a1 1 0 0 0-1-1H6z',
    capability: 'admin_console',
  },
  {
    path: '/settings',
    label: '系统设置',
    icon: 'M4 6h10v2H4V6zm12 0h4v2h-4V6zM4 11h6v2H4v-2zm8 0h8v2h-8v-2zM4 16h10v2H4v-2zm12 0h4v2h-4v-2z',
    capability: 'admin_console',
  },
]

const routeTitleMap: Record<string, string> = {
  dashboard: '概览中心',
  accounts: '账号管理',
  logs: '日志管理',
  gallery: '图片管理',
  proxy: '代理管理',
  settings: '系统设置',
  monitor: '实时监控',
  studio: '对话画图',
}

const visibleMenuItems = computed(() => {
  return menuItems.filter(item => authStore.hasCapability(item.capability))
})

const currentPageTitle = computed(() => {
  const routeName = String(route.name || '')
  const item = visibleMenuItems.value.find(item => isNavActive(item.path))
  return item?.label || routeTitleMap[routeName] || '概览中心'
})

const isImmersivePage = computed(() => Boolean(route.meta.immersive))
const isWorkspacePage = computed(() => Boolean(route.meta.workspace))
const isManagementPage = computed(() => Boolean(route.meta.management))
const { isWorkspaceLayout } = useListLayoutPreference()
const isContainedManagementPage = computed(() => isManagementPage.value && isWorkspaceLayout.value)
const usesViewportLayout = computed(() => isWorkspacePage.value || isContainedManagementPage.value)
const isMobileSidebarActive = computed(() => isMobileViewport.value && isSidebarOpen.value)
const isSidebarRail = computed(() => isSidebarCollapsed.value || isImmersivePage.value)
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

function buildNavItemClass(path: string) {
  const base = navItemBaseClass
  if (isNavActive(path)) {
    return `${base} rounded-[0.9rem] border-[hsl(var(--primary)_/_0.28)] bg-[hsl(var(--primary)_/_0.08)] font-semibold text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)_/_0.08)]`
  }
  return `${base} rounded-[0.9rem] border-transparent text-muted-foreground hover:border-border hover:bg-[hsl(var(--secondary)_/_0.55)] hover:text-foreground`
}

function buildNavIconClass(path: string) {
  if (isNavActive(path)) {
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
const apiKeyDisplay = computed(() => currentAuthToken.value || '未登录')
const currentVersionLabel = computed(() => normalizeVersionTag(currentVersionTag.value || ''))
const latestVersionLabel = computed(() => normalizeVersionTag(
  latestVersionTag.value || latestReleasedVersion(releaseEntries.value) || currentVersionTag.value || '',
))
const hasNewVersion = computed(() => isNewerVersion(latestVersionLabel.value, currentVersionLabel.value))
const updateCheckMessageClass = computed(() => {
  if (updateCheckStatus.value === 'available') return 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700'
  if (updateCheckStatus.value === 'checking') return 'border-cyan-500/35 bg-cyan-500/10 text-cyan-700'
  if (updateCheckStatus.value === 'warning') return 'border-amber-500/40 bg-amber-500/10 text-amber-700'
  return 'border-border bg-muted/40 text-muted-foreground'
})
const updateCheckBadgeText = computed(() => {
  if (updateCheckStatus.value === 'available') return '可更新'
  if (updateCheckStatus.value === 'checking') return '检查中'
  if (updateCheckStatus.value === 'warning') return '部分失败'
  return '已是最新'
})
const updateCheckBadgeTone = computed(() => {
  if (updateCheckStatus.value === 'available') return 'success'
  if (updateCheckStatus.value === 'checking') return 'info'
  if (updateCheckStatus.value === 'warning') return 'warning'
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
const canvasHref = computed(() => {
  const canvas = thirdPartyApps.value?.infinite_canvas
  const token = getAuthToken()
  if (!canvas?.enabled || !canvas.url.trim() || !token) return ''
  return buildThirdPartyHref(canvas.url, apiBaseUrl.value, token)
})
const themeButtonText = computed(() => themeOptions.find(option => option.value === themeMode.value)?.label || '系统')
const themeButtonTitle = computed(() => `当前主题：${themeButtonText.value}，点击切换`)
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
    label: 'QQ 交流群：1005859624',
    href: 'https://qm.qq.com/q/yegwCqJisS',
    icon: 'lucide:messages-square',
  },
  {
    key: 'service-account',
    label: '购买生图账号',
    href: 'https://pay.ldxp.cn/shop/yukkcat',
    icon: 'lucide:shopping-bag',
  },
  {
    key: 'service-api',
    label: '生图 API',
    detail: '个人 ¥0.02/张 · 中转 ¥0.01/张 · 大量/企业 ¥0.009/张',
    href: 'https://api.klong.lat',
    icon: 'lucide:badge-dollar-sign',
  },
]

const mobileHeaderMenuItems = computed<ActionMenuItem[]>(() => {
  const items: ActionMenuItem[] = []
  if (canvasHref.value) items.push({ key: 'canvas', label: '无限画布' })
  if (authStore.isAdmin) {
    items.push(
      { key: 'api-info', label: '接口信息' },
      { key: 'updates', label: '版本更新' },
    )
  }
  items.push({ key: 'services', label: '交流与服务', dividerBefore: items.length > 0 })
  return items
})
const routePendingText = computed(() => `正在加载${currentPageTitle.value}`)
let systemThemeMedia: MediaQueryList | null = null
let viewportMedia: MediaQueryList | null = null
const prefetchedRoutePaths = new Set<string>()
const releasePageUrl = 'https://github.com/yukkcat/chatgpt2api/releases'
const latestVersionUrl = 'https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/VERSION'
const latestChangelogUrl = 'https://raw.githubusercontent.com/yukkcat/chatgpt2api/main/CHANGELOG.md'
const updateCheckingMessage = '正在检查云端版本...'
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
    toast.success('已复制')
  } catch (error) {
    console.error('Copy failed', error)
    toast.error('复制失败，请手动复制')
  }
}

async function openInfiniteCanvas() {
  if (!canvasHref.value) return
  const ok = await confirmDialog.ask({
    title: '打开无限画布',
    message: '即将打开外部画布，并附带当前接口地址和当前调用密钥。是否继续？',
    confirmText: '打开',
    cancelText: '取消',
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
  updateCheckMessage.value = updateCheckingMessage
  updateCheckStatus.value = 'checking'
  void loadLocalReleaseEntries()
  void checkForUpdates(false)
}

function openReleasePage() {
  window.open(releasePageUrl, '_blank', 'noopener,noreferrer')
}

async function checkForUpdates(showMessage = true) {
  if (isCheckingUpdate.value) return
  isCheckingUpdate.value = true
  updateCheckStatus.value = 'checking'
  updateCheckMessage.value = updateCheckingMessage

  const [versionResult, changelogResult] = await Promise.allSettled([
    fetchRemoteText(latestVersionUrl),
    fetchRemoteText(latestChangelogUrl),
  ])

  if (versionResult.status === 'fulfilled') {
    latestVersionTag.value = normalizeVersionTag(versionResult.value)
  }
  if (changelogResult.status === 'fulfilled') {
    const remoteReleases = parseChangelog(changelogResult.value)
    if (remoteReleases.length) {
      releaseEntries.value = remoteReleases
      releaseEntriesSource.value = 'remote'
    }
  }

  const fullySuccessful = versionResult.status === 'fulfilled' && changelogResult.status === 'fulfilled'
  const fullyFailed = versionResult.status === 'rejected' && changelogResult.status === 'rejected'
  const newVersionAvailable = hasNewVersion.value
  if (fullyFailed) {
    updateCheckStatus.value = 'warning'
    updateCheckMessage.value = '云端版本与更新日志获取失败，当前展示本地信息。'
  } else if (!fullySuccessful) {
    updateCheckStatus.value = newVersionAvailable ? 'available' : 'warning'
    updateCheckMessage.value = newVersionAvailable
      ? `发现新版本：${latestVersionLabel.value}（部分云端信息获取失败）`
      : '部分云端信息获取失败，已展示可用的版本信息。'
  } else if (newVersionAvailable) {
    updateCheckStatus.value = 'available'
    updateCheckMessage.value = `发现新版本：${latestVersionLabel.value}`
  } else {
    updateCheckStatus.value = 'current'
    updateCheckMessage.value = `当前已是最新版本：${currentVersionLabel.value || latestVersionLabel.value}`
  }

  if (showMessage) {
    if (fullyFailed || !fullySuccessful) toast.warning(updateCheckMessage.value)
    else if (newVersionAvailable) toast.info(updateCheckMessage.value)
    else toast.success(updateCheckMessage.value)
  }
  isCheckingUpdate.value = false
}

async function fetchRemoteText(url: string) {
  const controller = new AbortController()
  const timeoutId = window.setTimeout(() => controller.abort(), 8000)
  try {
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal })
    if (!response.ok) throw new Error(`云端返回 ${response.status}`)
    return response.text()
  } finally {
    window.clearTimeout(timeoutId)
  }
}

async function loadLocalReleaseEntries() {
  if (releaseEntriesSource.value !== 'none') return
  try {
    const module = await import('../../../CHANGELOG.md?raw')
    const localReleases = parseChangelog(module.default || '')
    if (releaseEntriesSource.value === 'none') {
      releaseEntries.value = localReleases
      releaseEntriesSource.value = 'local'
    }
  } catch {
    if (releaseEntriesSource.value === 'none') {
      releaseEntries.value = []
    }
  }
}

async function loadCurrentVersion() {
  try {
    const result = await versionApi.current()
    const runtimeVersion = String(result.tag || '').trim()
    if (runtimeVersion) currentVersionTag.value = runtimeVersion
    if (!latestVersionTag.value) {
      latestVersionTag.value = normalizeVersionTag(latestReleasedVersion(releaseEntries.value) || currentVersionTag.value)
    }
  } catch {
    if (!latestVersionTag.value) {
      latestVersionTag.value = normalizeVersionTag(latestReleasedVersion(releaseEntries.value) || currentVersionTag.value)
    }
  }
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

function prefetchRouteView(path: string) {
  const normalizedPath = normalizedRoutePath(path)
  const loader = routeViewLoaders[normalizedPath]
  if (!loader || prefetchedRoutePaths.has(normalizedPath)) return
  prefetchedRoutePaths.add(normalizedPath)
  void loader().catch(() => {
    prefetchedRoutePaths.delete(normalizedPath)
  })
}

function handleNavClick() {
  closeSidebar()
}

onMounted(() => {
  applyThemeMode(themeMode.value)
  setupSystemThemeListener()
  setupViewportListener()
  window.addEventListener(PUBLIC_SETTINGS_CHANGED_EVENT, handlePublicSettingsChanged)
  window.addEventListener('keydown', handleWindowKeydown)
  void loadCurrentVersion()
  void loadPublicRuntimeConfig()
})

onBeforeUnmount(() => {
  window.removeEventListener(PUBLIC_SETTINGS_CHANGED_EVENT, handlePublicSettingsChanged)
  window.removeEventListener('keydown', handleWindowKeydown)
  systemThemeMedia?.removeEventListener('change', handleSystemThemeChange)
  systemThemeMedia = null
  teardownViewportListener()
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
