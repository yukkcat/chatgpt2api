<template>
  <div
    class="accounts-page relative"
    :class="{ 'lg:flex lg:min-h-0 lg:flex-1 lg:flex-col': isWorkspaceLayout }"
  >
    <PagePanel
      class="accounts-panel flex flex-col gap-5"
      :class="{ 'min-h-0 flex-1': isWorkspaceLayout }"
    >
      <div class="accounts-toolbar">
        <div class="accounts-toolbar-row accounts-toolbar-row-main">
          <FilterToolbar class="accounts-toolbar-filters" :bordered="false">
            <Input
              :model-value="keyword"
              type="text"
              placeholder="搜索账号 ID / 邮箱 / Token / 套餐 / 来源"
              block
              root-class="min-w-[14rem] flex-1 md:max-w-sm"
              @update:model-value="keyword = $event.trim()"
            />
            <GroupedSelectMenu
              v-model="statusFilter"
              :options="statusFilterOptions"
              placeholder="状态筛选"
              selected-indicator="none"
              aria-label="账号状态筛选"
            />
            <GroupedSelectMenu
              v-model="groupFilter"
              :options="groupFilterOptions"
              placeholder="账号组"
              selected-indicator="none"
              aria-label="账号组筛选"
            />
          </FilterToolbar>

          <div class="accounts-toolbar-view">
            <Checkbox
              v-if="viewMode === 'cards'"
              :model-value="allVisibleSelected"
              :indeterminate="someVisibleSelected"
              @update:model-value="toggleSelectAllVisible"
            >
              全选本页
            </Checkbox>
            <ViewModeSwitch
              :model-value="viewMode"
              list-label="列表视图"
              cards-label="卡片视图"
              @update:model-value="setViewMode"
            />
          </div>
        </div>

        <div class="accounts-toolbar-row accounts-toolbar-row-actions">
          <div class="accounts-toolbar-action-cluster">
            <FilterToolbar class="accounts-toolbar-group accounts-toolbar-group-ops" :bordered="false" gap="tight">
              <Button
                size="sm"
                variant="outline"
                :root-class="accountToolbarButtonClass"
                :disabled="accountGroupsLoading"
                @click="openAccountGroupsModal"
              >
                账号组管理
              </Button>
              <FloatingActionMenu
                label="导入 / 添加"
                :items="accountEntryItems"
                :disabled="importBusy || batchBusy || accountOperationBusy"
                align="left"
                :trigger-class="accountToolbarMenuClass"
                @select="handleAccountEntryAction"
              />
              <FloatingActionMenu
                label="导出"
                :items="exportMenuItems"
                :disabled="exportBusy"
                align="left"
                :trigger-class="accountToolbarMenuClass"
                @select="handleExportAction"
              />
              <FloatingActionMenu
                :label="batchMenuLabel"
                :items="batchMenuItems"
                :disabled="batchBusy || accountOperationBusy || accountAllTotal === 0"
                align="left"
                :trigger-class="accountToolbarMenuClass"
                @select="handleBatchAction"
              />
            </FilterToolbar>
          </div>

          <FilterToolbar class="accounts-toolbar-group accounts-toolbar-group-refresh" :bordered="false" gap="tight">
            <Button
              size="sm"
              variant="outline"
              :root-class="accountToolbarSecondaryClass"
              :disabled="loading"
              @click="loadData"
            >
              刷新列表
            </Button>
          </FilterToolbar>
        </div>
      </div>

      <PageLoadingState
        v-if="viewMode === 'cards' && loading && visibleAccounts.length === 0"
        title="正在加载账号"
        description="读取账号列表、分组和分页状态。"
      />

      <TableShell
        v-else-if="viewMode === 'list'"
        :scroll-mode="isWorkspaceLayout ? 'contained' : 'page'"
        sticky-header
        unframed
        :loading="loading && visibleAccounts.length === 0"
        loading-title="正在加载账号"
        loading-description="读取账号列表、分组和分页状态。"
        :show-empty="!loading && visibleAccounts.length === 0"
        :empty-colspan="10"
        :scroll-class="isWorkspaceLayout ? 'max-h-[min(36rem,60dvh)] lg:max-h-none' : ''"
        table-class="min-w-[980px] w-full"
        head-class="tracking-[0.16em]"
      >
        <template #head>
          <tr>
              <th class="w-12 py-2.5 pr-4">
                <Checkbox
                  :model-value="allVisibleSelected"
                  :indeterminate="someVisibleSelected"
                  @update:model-value="toggleSelectAllVisible"
                >
                  <span class="sr-only">全选当前页账号</span>
                </Checkbox>
              </th>
              <th class="py-2.5 pr-5">AT / RT</th>
              <th class="py-2.5 pr-5">来源 / 套餐</th>
              <th class="py-2.5 pr-5">状态</th>
              <th class="py-2.5 pr-5">账户信息</th>
              <th class="py-2.5 pr-5">创建时间</th>
              <th class="py-2.5 pr-5">图片额度</th>
              <th class="py-2.5 pr-5">恢复时间</th>
              <th class="py-2.5 pr-5">成功 / 失败</th>
              <th class="py-2.5 pr-3 text-right">操作</th>
          </tr>
        </template>
        <template #empty>
                <EmptyState
                  plain
                  title="暂无账号数据"
                  description="可以先用 OAuth 登录已有账号，也可以导入 Access Token、Session JSON 或账号 JSON 文件。"
                />
        </template>
        <AccountTableRow
              v-for="item in visibleAccounts"
              :key="item.id"
              :item="item"
              :selected="isSelected(item.id)"
              :syncing="syncingAccountIds.has(item.id)"
              :refreshing-access-token="refreshingAccessTokenAccountIds.has(item.id)"
              :busy="batchBusy || accountOperationBusy"
              :status-detail-card-class="accountStatusDetailCardClass"
              :status-detail-text="accountStatusDetailText"
              @toggle-select="toggleSelect"
              @copy-credential="copyAccountCredential"
              @edit="openEditModal"
              @test="openAccountTest"
              @toggle-enabled="toggleEnabled"
              @sync-account="syncAccount"
              @refresh-access-token="refreshAccessToken"
              @remove="removeAccount"
            />
      </TableShell>

      <div
        v-else
        class="accounts-card-results scrollbar-slim grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3"
        :class="isWorkspaceLayout ? 'accounts-card-results--contained min-h-0 flex-1 overflow-y-auto' : ''"
      >
        <div v-if="!loading && visibleAccounts.length === 0" class="col-span-full">
          <EmptyState
            plain
            title="暂无账号数据"
            description="可以先用 OAuth 登录已有账号，也可以导入 Access Token、Session JSON 或账号 JSON 文件。"
          />
        </div>

        <AccountGridCard
          v-for="item in visibleAccounts"
          :key="`${item.id}-card`"
          :item="item"
          :selected="isSelected(item.id)"
          :syncing="syncingAccountIds.has(item.id)"
          :refreshing-access-token="refreshingAccessTokenAccountIds.has(item.id)"
          :busy="batchBusy || accountOperationBusy"
          :status-detail-card-class="accountStatusDetailCardClass"
          :status-detail-text="accountStatusDetailText"
          @toggle-select="toggleSelect"
          @copy-credential="copyAccountCredential"
          @edit="openEditModal"
          @test="openAccountTest"
          @toggle-enabled="toggleEnabled"
          @sync-account="syncAccount"
          @refresh-access-token="refreshAccessToken"
          @remove="removeAccount"
        />
      </div>

      <ListPagination
        v-model:page="currentPage"
        v-model:page-size="pageSize"
        v-model:layout-mode="listLayoutMode"
        :total-count="accountListTotal"
        :page-size-options="pageSizeOptions"
        unit="个账号"
        :disabled="loading"
      >
        <template #summary="{ visibleCount, totalCount, unit }">
          <span>当前展示 {{ visibleCount }} / {{ totalCount }} {{ unit }}</span>
        </template>
      </ListPagination>
    </PagePanel>

    <AccountTestModal
      :open="showAccountTestModal"
      :account="accountTestAccount"
      :mode="accountTestMode"
      :model="accountTestModel"
      :prompt="accountTestPrompt"
      :model-options="accountTestModelOptions"
      :model-catalog-loading="accountTestModelCatalogLoading"
      :running="accountTestRunning"
      :result="accountTestResult"
      @close="closeAccountTest"
      @run="runAccountTest"
      @update:mode="setAccountTestMode"
      @update:model="accountTestModel = $event"
      @update:prompt="accountTestPrompt = $event"
    />

    <ModalShell
      :open="showModal"
      :aria-label="editingId ? '编辑账号' : '添加账号'"
      max-width="44rem"
      :z-index="120"
    >
            <ModalHeader
              :title="editingId ? '编辑账号' : '添加账号'"
              :bordered="false"
              :close-disabled="saving"
              compact
              @close="closeModal"
        />

            <ModalBody density="compact" class="space-y-3">
                <FormSection title="基础信息" surface="plain">
                  <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                    <label v-if="editingId" class="text-xs">
                      <span class="ui-field-label">账号 ID</span>
                      <Input :model-value="form.id" disabled block />
                    </label>
                    <label class="text-xs">
                      <span class="ui-field-label">套餐</span>
                      <Input
                        :model-value="form.type"
                        block
                        placeholder="留空表示未知（Free / Plus / Pro）"
                        @update:model-value="form.type = $event.trim()"
                      />
                    </label>
                  </div>
                </FormSection>

                <FormSection v-if="!editingId" surface="plain">
                  <label class="block text-xs">
                    <span class="ui-field-label">Access Token（必填）</span>
                    <textarea
                      v-model.trim="form.access_token"
                      rows="3"
                      class="ui-textarea-sm font-mono"
                      placeholder="粘贴完整 access token"
                    ></textarea>
                  </label>
                </FormSection>

                <FormSection title="调度属性" surface="plain">
                  <div class="grid grid-cols-1 gap-2 md:grid-cols-3">
                    <div class="text-xs">
                      <span class="ui-field-label">来源</span>
                      <GroupedSelectMenu
                        v-model="form.source_type"
                        :options="accountSourceOptions"
                        placeholder="来源"
                        selected-indicator="none"
                        aria-label="账号来源"
                        block
                      />
                    </div>
                    <label class="text-xs">
                      <span class="ui-field-label">图片额度</span>
                      <Input
                        :model-value="form.quota"
                        type="number"
                        block
                        placeholder="留空表示未知"
                        @update:model-value="form.quota = $event.trim()"
                      />
                    </label>
                    <label class="text-xs">
                      <span class="ui-field-label">账号组</span>
                      <GroupedSelectMenu
                        v-model="form.group_id"
                        :options="accountGroupOptions"
                        :disabled="accountGroupsLoading"
                        aria-label="账号组"
                        selected-indicator="none"
                        block
                      />
                    </label>
                    <div class="space-y-2 text-xs md:col-span-3">
                      <div class="grid grid-cols-1 gap-2 md:grid-cols-[11rem_minmax(0,1fr)]">
                        <label>
                          <span class="ui-field-label">代理模式</span>
                          <GroupedSelectMenu
                            :model-value="proxyMode"
                            :options="accountProxyModeOptions"
                            aria-label="代理模式"
                            selected-indicator="none"
                            block
                            @update:model-value="setProxyMode"
                          />
                        </label>

                        <label v-if="proxyMode === 'group'">
                          <span class="ui-field-label">代理组（多节点）</span>
                          <GroupedSelectMenu
                            :model-value="selectedProxyGroupId"
                            :options="proxyGroupOptions"
                            :disabled="accountGroupsLoading"
                            aria-label="代理组"
                            selected-indicator="none"
                            block
                            @update:model-value="selectProxyGroup"
                          />
                        </label>

                        <label v-else-if="proxyMode === 'custom'">
                          <span class="ui-field-label">自定义代理</span>
                          <Input
                            :model-value="customProxyInput"
                            block
                            root-class="font-mono"
                            placeholder="http://127.0.0.1:7890"
                            @update:model-value="setCustomProxyInput"
                          />
                        </label>

                        <SurfaceBox v-else tone="muted" dashed density="compact" class="flex min-h-[3.25rem] items-center">
                          {{ proxyMode === 'direct' ? '该账号强制直连，不读取账号组或默认出口。' : '该账号不单独指定代理，会按账号组代理、默认出口顺序回退。' }}
                        </SurfaceBox>
                      </div>

                      <SurfaceBox tone="muted" density="compact" class="flex flex-wrap items-center justify-between gap-2">
                        <div class="min-w-0">
                          <span class="ui-field-label">当前代理</span>
                          <p class="mt-1 max-w-full truncate text-xs text-foreground" :title="accountProxyPreview">{{ accountProxyPreview }}</p>
                        </div>
                        <div class="flex flex-wrap items-center gap-2">
                          <Button
                            v-if="proxyMode === 'group'"
                            size="xs"
                            variant="outline"
                            root-class="min-w-24 justify-center"
                            :disabled="accountGroupsLoading"
                            @click="loadAccountGroups()"
                          >
                            {{ accountGroupsLoading ? '刷新中...' : '刷新代理组' }}
                          </Button>
                          <Button
                            v-if="proxyMode !== 'direct'"
                            size="xs"
                            variant="outline"
                            root-class="min-w-24 justify-center"
                            :disabled="proxyTesting || accountGroupsLoading"
                            @click="testAccountProxy"
                          >
                            {{ proxyTesting ? '测试中...' : '测试当前代理' }}
                          </Button>
                          <span v-else class="text-[11px] text-muted-foreground">直连模式无需测试出口</span>
                        </div>
                      </SurfaceBox>
                    </div>
                  </div>
                </FormSection>
            </ModalBody>

            <ModalFooter :bordered="false">
              <Button size="xs" variant="primary" root-class="min-w-14 justify-center" :disabled="saving" @click="saveAccount">
                {{ saving ? '保存中...' : '保存' }}
              </Button>
            </ModalFooter>
    </ModalShell>

    <ModalShell
      :open="showAccountGroupsModal"
      aria-label="账号组管理"
      max-width="58rem"
      :z-index="130"
    >
            <ModalHeader
              title="账号组管理"
              subtitle="先创建账号组，再在账号列表勾选账号批量绑定。"
              :close-disabled="accountGroupSaving"
              compact
              @close="closeAccountGroupsModal"
            />

            <div class="grid grid-cols-1 gap-0 md:grid-cols-[18rem_1fr]">
              <div class="border-b border-border bg-muted/20 p-4 md:border-b-0 md:border-r">
                <div class="space-y-3">
                  <p class="text-sm font-medium text-foreground">
                    {{ editingAccountGroupId ? '编辑账号组' : '新建账号组' }}
                  </p>

                  <label class="block text-xs">
                    <span class="ui-field-label">账号组名称</span>
                    <Input
                      :model-value="accountGroupForm.name"
                      block
                      placeholder="高额度账号 / Codex / 手动 Token"
                      @update:model-value="accountGroupForm.name = $event.trim()"
                    />
                  </label>

                  <div class="space-y-2 text-xs">
                    <label class="block">
                      <span class="ui-field-label">默认出口</span>
                      <GroupedSelectMenu
                        :model-value="accountGroupProxyMode"
                        :options="accountProxyModeOptions"
                        aria-label="账号组默认代理模式"
                        selected-indicator="none"
                        block
                        @update:model-value="setAccountGroupProxyMode"
                      />
                    </label>

                    <label v-if="accountGroupProxyMode === 'group'" class="block">
                      <span class="ui-field-label">代理组（多节点）</span>
                      <GroupedSelectMenu
                        :model-value="selectedAccountGroupProxyGroupId"
                        :options="accountGroupProxyOptions"
                        :disabled="accountGroupsLoading"
                        aria-label="账号组默认代理组"
                        selected-indicator="none"
                        block
                        @update:model-value="selectAccountGroupProxyGroup"
                      />
                    </label>

                    <label v-else-if="accountGroupProxyMode === 'custom'" class="block">
                      <span class="ui-field-label">自定义代理</span>
                      <Input
                        :model-value="accountGroupCustomProxyInput"
                        block
                        root-class="font-mono"
                        placeholder="http://127.0.0.1:7890"
                        @update:model-value="setAccountGroupCustomProxyInput"
                      />
                    </label>

                    <SurfaceBox v-else tone="muted" dashed density="compact" class="min-h-[2.75rem]">
                      {{ accountGroupProxyMode === 'direct' ? '该账号组强制直连，组内账号不会回退默认出口。' : '账号组不单独指定代理，组内账号会继续回退默认出口。' }}
                    </SurfaceBox>

                    <SurfaceBox tone="muted" density="compact">
                      <span class="ui-field-label">当前代理</span>
                      <p class="mt-1 truncate text-xs text-foreground" :title="accountGroupProxyPreview">{{ accountGroupProxyPreview }}</p>
                    </SurfaceBox>
                  </div>

                  <SurfaceBox tag="label" density="compact" class="flex items-center gap-2">
                    <Checkbox
                      :model-value="accountGroupForm.enabled"
                      @update:model-value="accountGroupForm.enabled = Boolean($event)"
                    />
                    启用账号组
                  </SurfaceBox>

                  <label class="block text-xs">
                    <span class="ui-field-label">备注</span>
                    <textarea
                      v-model.trim="accountGroupForm.notes"
                      rows="3"
                      class="ui-textarea-sm"
                      placeholder="例如：高额度账号默认走香港代理池"
                    ></textarea>
                  </label>

                  <Button size="sm" variant="primary" root-class="w-full justify-center" :disabled="accountGroupSaving" @click="saveAccountGroup">
                    {{ accountGroupSaving ? '保存中...' : editingAccountGroupId ? '保存账号组' : '创建账号组' }}
                  </Button>
                </div>
              </div>

              <div class="max-h-[32rem] overflow-y-auto p-4">
                <StateBlock v-if="accountGroupRows.length === 0" dashed>
                  还没有账号组。先在左侧创建，比如高额度账号、Codex、手动 Token。
                </StateBlock>

                <div v-else class="space-y-2">
                  <InfoCard
                    v-for="group in accountGroupRows"
                    :key="group.id"
                    tag="article"
                    density="compact"
                  >
                    <div class="flex flex-wrap items-start justify-between gap-3">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                          <p class="font-medium text-foreground">{{ group.name }}</p>
                          <StateBadge :tone="group.enabled ? 'success' : 'muted'" size="xs">
                            {{ group.enabled ? '启用' : '停用' }}
                          </StateBadge>
                        </div>
                        <p class="mt-1 text-xs text-muted-foreground">
                          {{ group.account_count }} 个账号 · 默认出口：{{ group.proxy_label }}
                        </p>
                        <p v-if="group.notes" class="mt-1 line-clamp-2 text-xs text-muted-foreground">{{ group.notes }}</p>
                      </div>

                      <div class="flex shrink-0 items-center gap-2">
                        <Button size="xs" variant="outline" :disabled="accountGroupSaving" @click="editAccountGroup(group.raw)">
                          编辑
                        </Button>
                        <Button size="xs" variant="outline" root-class="text-rose-600" :disabled="accountGroupSaving" @click="deleteAccountGroup(group.raw)">
                          删除
                        </Button>
                      </div>
                    </div>
                  </InfoCard>
                </div>
              </div>
            </div>
    </ModalShell>

    <ModalShell
      :open="showImportModal"
      aria-label="导入账号"
      max-width="58rem"
      :z-index="120"
    >
            <ModalHeader title="导入账号" :close-disabled="importModalBusy" compact @close="closeImportModal" />

            <div class="grid grid-cols-1 gap-0 md:grid-cols-[15rem_1fr]">
              <div class="border-b border-border bg-muted/20 p-3 md:border-b-0 md:border-r">
                <div class="space-y-1">
                  <button
                    v-for="option in importModeOptions"
                    :key="option.value"
                    type="button"
                    class="w-full rounded-xl px-3 py-2 text-left text-sm transition-colors"
                    :class="importMode === option.value ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-card hover:text-foreground'"
                    :disabled="importModalBusy"
                    @click="setImportMode(option.value)"
                  >
                    {{ option.label }}
                  </button>
                </div>
              </div>

              <div class="min-h-[26rem] p-4">
                <div v-if="importMode === 'oauth_login'" class="space-y-3">
                  <ImportModePanel
                    title="OAuth 登录已有账号"
                    description="用浏览器登录 ChatGPT，回填 callback URL 后保存 RT，用于 AT 临期自动续期。"
                  />
                  <div class="grid grid-cols-1 gap-3">
                    <label class="block text-xs">
                      <span class="ui-field-label">账号邮箱（可选）</span>
                      <Input
                        :model-value="oauthEmailHint"
                        type="email"
                        block
                        placeholder="name@example.com"
                        :disabled="importBusy"
                        @update:model-value="oauthEmailHint = $event.trim()"
                      />
                    </label>

                    <div class="flex flex-wrap gap-2">
                      <Button size="xs" variant="primary" :disabled="importBusy" @click="startOAuthLogin">
                        {{ oauthAuthorizeUrl ? '重新生成授权链接' : '生成并打开授权页面' }}
                      </Button>
                      <Button v-if="oauthAuthorizeUrl" size="xs" variant="outline" :disabled="importBusy" @click="openOAuthAuthorizeUrl">
                        打开授权页面
                      </Button>
                      <Button v-if="oauthAuthorizeUrl" size="xs" variant="outline" :disabled="importBusy" @click="copyOAuthAuthorizeUrl">
                        复制授权链接
                      </Button>
                    </div>

                    <SurfaceBox v-if="oauthAuthorizeUrl" tone="muted" density="compact" wrap>
                      授权链接已生成。登录完成后，把浏览器最终跳转到的 callback URL 粘贴到下方。
                      <span v-if="oauthRedirectUriPrefix">目标地址：{{ oauthRedirectUriPrefix }}</span>
                    </SurfaceBox>

                    <label class="block text-xs">
                      <span class="ui-field-label">Callback URL / Code</span>
                      <textarea
                        v-model.trim="oauthCallbackText"
                        rows="5"
                        class="ui-textarea-sm font-mono"
                        placeholder="粘贴完整 callback URL，或只粘贴 code"
                        :disabled="importBusy || !oauthSessionId"
                      ></textarea>
                    </label>

                    <div class="flex justify-end">
                      <Button
                        size="xs"
                        variant="primary"
                        :disabled="importBusy || !oauthSessionId || !oauthCallbackText.trim()"
                        @click="finishOAuthLogin"
                      >
                        {{ importBusy ? '导入中...' : '完成导入' }}
                      </Button>
                    </div>
                  </div>
                </div>

                <div v-else-if="importMode === 'access_token'" class="space-y-3">
                  <ImportModePanel
                    title="导入 Access Token"
                    description="支持直接粘贴，一行一个；也支持从 TXT 文件读取，一行一个。"
                  />
                  <textarea
                    v-model.trim="manualTokenText"
                    rows="10"
                    class="ui-textarea-sm font-mono"
                    placeholder="一行一个 access token"
                  ></textarea>
                  <div class="flex flex-wrap justify-end gap-2">
                    <Button size="xs" variant="outline" :disabled="importBusy" @click="openManualTokenFile">
                      读取 TXT 文件
                    </Button>
                    <Button size="xs" variant="primary" :disabled="importBusy || !manualTokenText.trim()" @click="importManualTokenText">
                      {{ importBusy ? '导入中...' : '开始导入' }}
                    </Button>
                  </div>
                </div>

                <div v-else-if="importMode === 'session_json'" class="space-y-3">
                  <ImportModePanel title="导入 Session JSON">
                    <template #description>
                      <p class="mt-1 text-xs leading-6 text-muted-foreground">
                        打开
                        <a
                          href="https://chatgpt.com/api/auth/session"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="font-medium text-primary underline decoration-primary/35 underline-offset-2 hover:decoration-primary"
                        >https://chatgpt.com/api/auth/session</a>，复制完整 JSON，系统会自动提取 accessToken；该接口通常不包含长期 refresh_token。
                      </p>
                    </template>
                  </ImportModePanel>
                  <textarea v-model.trim="sessionJsonText" rows="12" class="ui-textarea-sm font-mono" placeholder="粘贴完整 session JSON"></textarea>
                  <div class="flex justify-end">
                    <Button size="xs" variant="primary" :disabled="importBusy || !sessionJsonText.trim()" @click="importSessionJson">
                      {{ importBusy ? '导入中...' : '开始导入' }}
                    </Button>
                  </div>
                </div>

                <div v-else-if="importMode === 'backup_json'" class="space-y-3">
                  <ImportModePanel
                    title="导入完整备份文件"
                    description="读取本系统导出的完整账号 JSON，直接恢复已保存的凭据和账号配置，不请求远程接口验证。"
                  />
                  <StateBlock dashed compact>
                    <Button size="sm" variant="outline" :disabled="importBusy" @click="openCPAFileDialog">
                      选择备份 JSON 文件
                    </Button>
                  </StateBlock>
                </div>

                <div v-else-if="importMode === 'cpa_json'" class="space-y-3">
                  <ImportModePanel
                    title="导入 CPA JSON 文件"
                    description="从一个或多个 CPA JSON 文件提取账号凭据，并请求远程接口验证、同步账号信息与额度。"
                  />
                  <StateBlock dashed compact>
                    <Button size="sm" variant="outline" :disabled="importBusy" @click="openCPAFileDialog">
                      选择 CPA JSON 文件
                    </Button>
                  </StateBlock>
                </div>

                <div v-else-if="importMode === 'remote_cpa'" class="space-y-3">
                  <RemoteAccountImportPanel
                    mode="cpa"
                    external-tracking
                    @busy-change="remoteImportBusy = $event"
                    @progress="updateRemoteImportProgress"
                    @started="startRemoteImportTracking"
                  />
                </div>

                <div v-else-if="importMode === 'sub2api'" class="space-y-3">
                  <RemoteAccountImportPanel
                    mode="sub2api"
                    external-tracking
                    @busy-change="remoteImportBusy = $event"
                    @progress="updateRemoteImportProgress"
                    @started="startRemoteImportTracking"
                  />
                </div>
              </div>
            </div>
    </ModalShell>

    <AccountOperationDrawer
      :open="showRefreshProgress"
      :title="refreshProgressTitle"
      :status-text="refreshProgressStatusText"
      :progress="refreshProgress"
      :percent="refreshProgressPercent"
      :events="accountOperationEvents"
      :can-stop="canStopRefreshProgress"
      :stop-requested="bulkStopRequested"
      :can-close="canCloseRefreshProgress"
      @stop="requestStopRefreshProgress"
      @close="closeRefreshProgress"
    />

    <input ref="manualTokenFileInputRef" type="file" accept=".txt,text/plain" class="hidden" @change="handleManualTokenFileChange" />
    <input ref="cpaFileInputRef" type="file" accept=".json,application/json" multiple class="hidden" @change="handleCPAFileChange" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { Button, Checkbox, EmptyState, GroupedSelectMenu, Input, TableShell, ViewModeSwitch } from 'nanocat-ui'
import FilterToolbar from '@/components/ai/FilterToolbar.vue'
import FloatingActionMenu from '@/components/ai/FloatingActionMenu.vue'
import FormSection from '@/components/ai/FormSection.vue'
import ImportModePanel from '@/components/ai/ImportModePanel.vue'
import InfoCard from '@/components/ai/InfoCard.vue'
import ListPagination from '@/components/ai/ListPagination.vue'
import ModalBody from '@/components/ai/ModalBody.vue'
import ModalFooter from '@/components/ai/ModalFooter.vue'
import ModalHeader from '@/components/ai/ModalHeader.vue'
import ModalShell from '@/components/ai/ModalShell.vue'
import PageLoadingState from '@/components/ai/PageLoadingState.vue'
import PagePanel from '@/components/ai/PagePanel.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import StateBlock from '@/components/ai/StateBlock.vue'
import SurfaceBox from '@/components/ai/SurfaceBox.vue'
import type { Account } from '@/api/accounts'
import AccountGridCard from './accounts/AccountGridCard.vue'
import AccountOperationDrawer from './accounts/AccountOperationDrawer.vue'
import AccountTestModal from './accounts/AccountTestModal.vue'
import AccountTableRow from './accounts/AccountTableRow.vue'
import { useAccountsPage } from './accounts/useAccountsPage'
import { useListLayoutPreference } from '@/composables/useListLayoutPreference'
import { useAccountActionMenuRuntime } from './accounts/accountActionMenuRuntime'
import {
  accountGroupLabel as buildAccountGroupLabel,
  accountGroupNameMap as buildAccountGroupNameMap,
  accountProxyText,
  accountStatusDetailText as buildAccountStatusDetailText,
  buildAccountGroupRows,
} from './accounts/viewUtils'

defineOptions({ name: 'Accounts' })

const RemoteAccountImportPanel = defineAsyncComponent(() => import('@/components/ai/RemoteAccountImportPanel.vue'))

const {
  loading,
  saving,
  showModal,
  showAccountTestModal,
  accountTestAccount,
  accountTestMode,
  accountTestModel,
  accountTestPrompt,
  accountTestRunning,
  accountTestResult,
  accountTestModelOptions,
  accountTestModelCatalogLoading,
  keyword,
  statusFilter,
  groupFilter,
  statusFilterOptions,
  groupFilterOptions,
  editingId,
  accounts,
  accountListTotal,
  accountAllTotal,
  selectedCount,
  allVisibleSelected,
  someVisibleSelected,
  currentPage,
  pageSize,
  pageSizeOptions,
  batchBusy,
  viewMode,
  syncingAccountIds,
  refreshingAccessTokenAccountIds,
  accountOperationBusy,
  importBusy,
  exportBusy,
  showImportModal,
  importMode,
  importModeOptions,
  oauthEmailHint,
  oauthCallbackText,
  oauthSessionId,
  oauthAuthorizeUrl,
  oauthRedirectUriPrefix,
  manualTokenText,
  sessionJsonText,
  accountGroups,
  proxyGroups,
  accountGroupsLoading,
  showAccountGroupsModal,
  accountGroupSaving,
  editingAccountGroupId,
  accountGroupForm,
  accountGroupOptions,
  accountGroupProxyOptions,
  bindAccountGroupOptions,
  selectedBindGroupId,
  proxyTesting,
  proxyMode,
  accountGroupProxyMode,
  accountProxyModeOptions,
  proxyGroupOptions,
  selectedProxyGroupId,
  customProxyInput,
  selectedAccountGroupProxyGroupId,
  accountGroupCustomProxyInput,
  accountProxyPreview,
  accountGroupProxyPreview,
  showRefreshProgress,
  refreshProgressTitle,
  refreshProgress,
  refreshProgressPercent,
  refreshProgressStatusText,
  canStopRefreshProgress,
  canCloseRefreshProgress,
  bulkStopRequested,
  accountOperationEvents,
  form,
  visibleAccounts,
  loadData,
  loadAccountGroups,
  setViewMode,
  isSelected,
  toggleSelect,
  clearSelection,
  selectAllAccounts,
  toggleSelectAllVisible,
  setImportMode,
  openImportModal,
  closeImportModal,
  testAccountProxy,
  openAccountGroupsModal,
  closeAccountGroupsModal,
  resetAccountGroupForm,
  editAccountGroup,
  saveAccountGroup,
  deleteAccountGroup,
  setProxyMode,
  selectProxyGroup,
  setCustomProxyInput,
  setAccountGroupProxyMode,
  selectAccountGroupProxyGroup,
  setAccountGroupCustomProxyInput,
  importManualTokenText,
  importTokenTextFile,
  importSessionJson,
  startOAuthLogin,
  openOAuthAuthorizeUrl,
  copyOAuthAuthorizeUrl,
  finishOAuthLogin,
  importLocalCPAFiles,
  updateRemoteImportProgress,
  startRemoteImportTracking,
  requestStopRefreshProgress,
  closeRefreshProgress,
  copyAccountCredential,
  openCreateModal,
  openEditModal,
  openAccountTest,
  closeAccountTest,
  setAccountTestMode,
  runAccountTest,
  closeModal,
  saveAccount,
  toggleEnabled,
  syncAccount,
  refreshAccessToken,
  removeAccount,
  runBulkAction,
  bindSelectedAccountsToGroup,
  exportAccounts,
} = useAccountsPage()

const { listLayoutMode, isWorkspaceLayout } = useListLayoutPreference()

watch(
  [showModal, showImportModal, showAccountGroupsModal, showAccountTestModal],
  ([accountModalOpen, importModalOpen, groupsModalOpen, testModalOpen]) => {
    if (!accountModalOpen && !importModalOpen && !groupsModalOpen && !testModalOpen) return
    if (canCloseRefreshProgress.value) closeRefreshProgress()
  },
)

const manualTokenFileInputRef = ref<HTMLInputElement | null>(null)
const cpaFileInputRef = ref<HTMLInputElement | null>(null)
const remoteImportBusy = ref(false)
const accountToolbarMenuClass = 'shrink-0 whitespace-nowrap'
const accountToolbarButtonClass = 'shrink-0 whitespace-nowrap justify-between gap-2'
const accountStatusDetailCardClass = 'w-72 account-status-detail-card'
const accountToolbarSecondaryClass = `${accountToolbarButtonClass} text-muted-foreground`
const accountSourceOptions = [
  { label: 'Web', value: 'web' },
  { label: 'Codex', value: 'codex' },
] as const
const importModalBusy = computed(() => importBusy.value || remoteImportBusy.value)

const accountGroupNameMap = computed(() => buildAccountGroupNameMap(accountGroups.value))

const accountGroupRows = computed(() => buildAccountGroupRows(accountGroups.value))

function accountGroupLabel(groupId: string | undefined) {
  return buildAccountGroupLabel(groupId, accountGroupNameMap.value)
}

function accountStatusDetailText(item: Account) {
  return buildAccountStatusDetailText(item, accountGroupLabel, accountProxyText)
}

const {
  accountEntryItems,
  exportMenuItems,
  batchMenuItems,
  batchMenuLabel,
  handleBatchAction,
  handleAccountEntryAction,
  handleExportAction,
} = useAccountActionMenuRuntime({
  selectedCount,
  accountAllTotal,
  accountGroupsLoading,
  bindAccountGroupOptions,
  selectedBindGroupId,
  openCreateModal,
  openImportModal,
  exportAccounts,
  runBulkAction,
  bindSelectedAccountsToGroup,
  selectAllAccounts,
  clearSelection,
})

function openManualTokenFile() {
  if (!manualTokenFileInputRef.value || importBusy.value) return
  manualTokenFileInputRef.value.value = ''
  manualTokenFileInputRef.value.click()
}

async function handleManualTokenFileChange(event: Event) {
  const target = event.target as HTMLInputElement | null
  const file = target?.files?.[0]
  await importTokenTextFile(file)
  if (target) target.value = ''
}

function openCPAFileDialog() {
  if (!cpaFileInputRef.value || importBusy.value) return
  cpaFileInputRef.value.value = ''
  cpaFileInputRef.value.click()
}

async function handleCPAFileChange(event: Event) {
  const target = event.target as HTMLInputElement | null
  await importLocalCPAFiles(target?.files)
  if (target) target.value = ''
}

</script>

<style scoped>
.accounts-toolbar {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.accounts-card-results--contained {
  max-height: min(36rem, 60dvh);
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
}

@media (min-width: 1024px) {
  .accounts-card-results--contained {
    max-height: none;
  }
}

.accounts-toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.accounts-toolbar-row-main {
  justify-content: space-between;
}

.accounts-toolbar-row-actions {
  align-items: flex-start;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid hsl(var(--border) / 0.62);
}

.accounts-toolbar-filters {
  min-width: min(100%, 34rem);
  flex: 1 1 34rem;
}

.accounts-toolbar-view {
  display: flex;
  min-height: 2rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.accounts-toolbar-group {
  min-width: 0;
}

.accounts-toolbar-action-cluster {
  display: flex;
  min-width: 0;
  flex: 1 1 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

.accounts-toolbar-group-ops {
  flex: 0 1 auto;
}

.accounts-toolbar-group-refresh {
  margin-left: auto;
  justify-content: flex-end;
}

@media (max-width: 900px) {
  .accounts-toolbar-view {
    width: 100%;
    justify-content: flex-start;
  }

  .accounts-toolbar-group-refresh {
    width: 100%;
    margin-left: 0;
    justify-content: flex-start;
  }
}
</style>
