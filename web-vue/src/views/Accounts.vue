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
              placeholder="Search account ID / email / token / plan / source"
              block
              root-class="min-w-[14rem] flex-1 md:max-w-sm"
              @update:model-value="keyword = $event.trim()"
            />
            <GroupedSelectMenu
              v-model="statusFilter"
              :options="statusFilterOptions"
              placeholder="Filter by status"
              selected-indicator="none"
              aria-label="Filter accounts by status"
            />
            <GroupedSelectMenu
              v-model="groupFilter"
              :options="groupFilterOptions"
              placeholder="Account group"
              selected-indicator="none"
              aria-label="Filter by account group"
            />
          </FilterToolbar>

          <div class="accounts-toolbar-view">
            <Checkbox
              v-if="viewMode === 'cards'"
              :model-value="allVisibleSelected"
              :indeterminate="someVisibleSelected"
              @update:model-value="toggleSelectAllVisible"
            >
              Select current page
            </Checkbox>
            <ViewModeSwitch
              :model-value="viewMode"
              list-label="List view"
              cards-label="Card view"
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
                Manage groups
              </Button>
              <FloatingActionMenu
                label="Import / add"
                :items="accountEntryItems"
                :disabled="importBusy || batchBusy || accountOperationBusy"
                align="left"
                :trigger-class="accountToolbarMenuClass"
                @select="handleAccountEntryAction"
              />
              <FloatingActionMenu
                label="Export"
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
              Refresh list
            </Button>
          </FilterToolbar>
        </div>
      </div>

      <PageLoadingState
        v-if="viewMode === 'cards' && loading && visibleAccounts.length === 0"
        title="Loading accounts"
        description="Loading the account list, groups, and pagination state."
      />

      <TableShell
        v-else-if="viewMode === 'list'"
        :scroll-mode="isWorkspaceLayout ? 'contained' : 'page'"
        sticky-header
        unframed
        :loading="loading && visibleAccounts.length === 0"
        loading-title="Loading accounts"
        loading-description="Loading the account list, groups, and pagination state."
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
                  <span class="sr-only">Select all accounts on this page</span>
                </Checkbox>
              </th>
              <th class="py-2.5 pr-5">AT / RT</th>
              <th class="py-2.5 pr-5">Source / plan</th>
              <th class="py-2.5 pr-5">Status</th>
              <th class="py-2.5 pr-5">Account details</th>
              <th class="py-2.5 pr-5">Created</th>
              <th class="py-2.5 pr-5">Image quota</th>
              <th class="py-2.5 pr-5">Reset time</th>
              <th class="py-2.5 pr-5">Success / failure</th>
              <th class="py-2.5 pr-3 text-right">Actions</th>
          </tr>
        </template>
        <template #empty>
                <EmptyState
                  plain
                  title="No accounts yet"
                  description="Sign in to an existing account with OAuth, or import an access token, session JSON, or account JSON file."
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
            title="No accounts yet"
            description="Sign in to an existing account with OAuth, or import an access token, session JSON, or account JSON file."
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
        unit="accounts"
        :disabled="loading"
      >
        <template #summary="{ visibleCount, totalCount, unit }">
          <span>Showing {{ visibleCount }} / {{ totalCount }} {{ unit }}</span>
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
      :aria-label="editingId ? 'Edit account' : 'Add account'"
      :z-index="120"
    >
            <ModalHeader
              :title="editingId ? 'Edit account' : 'Add account'"
              :bordered="false"
              :close-disabled="saving"
              compact
              @close="closeModal"
        />

            <ModalBody density="compact" class="space-y-3">
                <FormSection v-if="editingId" title="Account identity" surface="plain">
                  <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                    <label class="text-xs">
                      <span class="ui-field-label">Email</span>
                      <Input :model-value="form.email || 'Not available'" disabled block />
                    </label>
                    <label class="text-xs">
                      <span class="ui-field-label">Admin ID</span>
                      <Input :model-value="form.id" disabled block root-class="font-mono" />
                    </label>
                  </div>
                </FormSection>

                <FormSection title="Account credentials" surface="plain">
                  <div class="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                  <label class="block text-xs">
                    <span class="ui-field-label">AT{{ editingId ? '' : ' (required)' }}</span>
                    <textarea
                      v-model.trim="form.access_token"
                      rows="3"
                      class="ui-textarea-sm font-mono"
                      :placeholder="editingId ? 'Leave blank to keep unchanged' : 'Paste the full access token'"
                      autocomplete="off"
                      spellcheck="false"
                    ></textarea>
                  </label>
                  <label class="block text-xs">
                    <span class="ui-field-label">RT (optional)</span>
                    <textarea
                      v-model.trim="form.refresh_token"
                      rows="3"
                      class="ui-textarea-sm font-mono"
                      :placeholder="editingId ? 'Leave blank to keep unchanged' : 'Paste the refresh token'"
                      autocomplete="off"
                      spellcheck="false"
                    ></textarea>
                  </label>
                  </div>
                </FormSection>

                <FormSection title="Account settings" surface="plain">
                  <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <label class="text-xs">
                      <span class="ui-field-label">Plan</span>
                      <Input
                        :model-value="form.type"
                        block
                        placeholder="Leave blank if unknown (Free / Plus / Pro)"
                        @update:model-value="form.type = $event.trim()"
                      />
                    </label>
                    <div class="text-xs">
                      <span class="ui-field-label">Source</span>
                      <GroupedSelectMenu
                        v-model="form.source_type"
                        :options="accountSourceOptions"
                        placeholder="Source"
                        selected-indicator="none"
                        aria-label="Account source"
                        block
                      />
                    </div>
                    <label class="text-xs">
                      <span class="ui-field-label">Image quota</span>
                      <Input
                        :model-value="form.quota"
                        type="number"
                        block
                        placeholder="Leave blank if unknown"
                        @update:model-value="form.quota = $event.trim()"
                      />
                    </label>
                    <label class="text-xs">
                      <span class="ui-field-label">Account group</span>
                      <GroupedSelectMenu
                        v-model="form.group_id"
                        :options="accountGroupOptions"
                        :disabled="accountGroupsLoading"
                        aria-label="Account group"
                        selected-indicator="none"
                        block
                      />
                    </label>
                    <div class="space-y-2 text-xs md:col-span-2">
                      <div class="grid grid-cols-1 gap-2 md:grid-cols-[11rem_minmax(0,1fr)]">
                        <label>
                          <span class="ui-field-label">Proxy mode</span>
                          <GroupedSelectMenu
                            :model-value="proxyMode"
                            :options="accountProxyModeOptions"
                            aria-label="Proxy mode"
                            selected-indicator="none"
                            block
                            @update:model-value="setProxyMode"
                          />
                        </label>

                        <label v-if="proxyMode === 'group'">
                          <span class="ui-field-label">Proxy group (multiple nodes)</span>
                          <GroupedSelectMenu
                            :model-value="selectedProxyGroupId"
                            :options="proxyGroupOptions"
                            :disabled="accountGroupsLoading"
                            aria-label="Proxy group"
                            selected-indicator="none"
                            block
                            @update:model-value="selectProxyGroup"
                          />
                        </label>

                        <label v-else-if="proxyMode === 'custom'">
                          <span class="ui-field-label">Custom proxy</span>
                          <Input
                            :model-value="customProxyInput"
                            block
                            root-class="font-mono"
                            placeholder="http://127.0.0.1:7890"
                            @update:model-value="setCustomProxyInput"
                          />
                        </label>

                        <SurfaceBox v-else tone="muted" dashed density="compact" class="flex min-h-[3.25rem] items-center">
                          {{ proxyMode === 'direct' ? 'This account always connects directly and ignores its group and default proxy.' : 'No proxy is set for this account. It falls back to the group proxy, then the default proxy.' }}
                        </SurfaceBox>
                      </div>

                      <SurfaceBox tone="muted" density="compact" class="flex flex-wrap items-center justify-between gap-2">
                        <div class="min-w-0">
                          <span class="ui-field-label">Current proxy</span>
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
                            {{ accountGroupsLoading ? 'Refreshing…' : 'Refresh proxy groups' }}
                          </Button>
                          <Button
                            v-if="proxyMode !== 'direct'"
                            size="xs"
                            variant="outline"
                            root-class="min-w-24 justify-center"
                            :disabled="proxyTesting || accountGroupsLoading"
                            @click="testAccountProxy"
                          >
                            {{ proxyTesting ? 'Testing…' : 'Test current proxy' }}
                          </Button>
                          <span v-else class="text-[11px] text-muted-foreground">No proxy test is needed in direct mode.</span>
                        </div>
                      </SurfaceBox>
                    </div>
                  </div>
                </FormSection>
            </ModalBody>

            <ModalFooter :bordered="false">
              <Button size="xs" variant="primary" root-class="min-w-14 justify-center" :disabled="saving" @click="saveAccount">
                {{ saving ? 'Saving…' : 'Save' }}
              </Button>
            </ModalFooter>
    </ModalShell>

    <ModalShell
      :open="showAccountGroupsModal"
      aria-label="Manage account groups"
      :z-index="130"
    >
            <ModalHeader
              title="Manage account groups"
              subtitle="Create a group, then select accounts in the list to bind them in bulk."
              :close-disabled="accountGroupSaving"
              compact
              @close="closeAccountGroupsModal"
            />

            <div class="grid grid-cols-1 gap-0 md:grid-cols-[18rem_1fr]">
              <div class="border-b border-border bg-muted/20 p-4 md:border-b-0 md:border-r">
                <div class="space-y-3">
                  <p class="text-sm font-medium text-foreground">
                    {{ editingAccountGroupId ? 'Edit group' : 'Create group' }}
                  </p>

                  <label class="block text-xs">
                    <span class="ui-field-label">Group name</span>
                    <Input
                      :model-value="accountGroupForm.name"
                      block
                      placeholder="High-quota accounts / Codex / manual tokens"
                      @update:model-value="accountGroupForm.name = $event.trim()"
                    />
                  </label>

                  <div class="space-y-2 text-xs">
                    <label class="block">
                      <span class="ui-field-label">Default proxy</span>
                      <GroupedSelectMenu
                        :model-value="accountGroupProxyMode"
                        :options="accountProxyModeOptions"
                        aria-label="Group default proxy mode"
                        selected-indicator="none"
                        block
                        @update:model-value="setAccountGroupProxyMode"
                      />
                    </label>

                    <label v-if="accountGroupProxyMode === 'group'" class="block">
                      <span class="ui-field-label">Proxy group (multiple nodes)</span>
                      <GroupedSelectMenu
                        :model-value="selectedAccountGroupProxyGroupId"
                        :options="accountGroupProxyOptions"
                        :disabled="accountGroupsLoading"
                        aria-label="Group default proxy group"
                        selected-indicator="none"
                        block
                        @update:model-value="selectAccountGroupProxyGroup"
                      />
                    </label>

                    <label v-else-if="accountGroupProxyMode === 'custom'" class="block">
                      <span class="ui-field-label">Custom proxy</span>
                      <Input
                        :model-value="accountGroupCustomProxyInput"
                        block
                        root-class="font-mono"
                        placeholder="http://127.0.0.1:7890"
                        @update:model-value="setAccountGroupCustomProxyInput"
                      />
                    </label>

                    <SurfaceBox v-else tone="muted" dashed density="compact" class="min-h-[2.75rem]">
                      {{ accountGroupProxyMode === 'direct' ? 'This group always connects directly. Its accounts will not fall back to the default proxy.' : 'No proxy is set for this group. Its accounts continue to use the default proxy as a fallback.' }}
                    </SurfaceBox>

                    <SurfaceBox tone="muted" density="compact">
                      <span class="ui-field-label">Current proxy</span>
                      <p class="mt-1 truncate text-xs text-foreground" :title="accountGroupProxyPreview">{{ accountGroupProxyPreview }}</p>
                    </SurfaceBox>
                  </div>

                  <SurfaceBox tag="label" density="compact" class="flex items-center gap-2">
                    <Checkbox
                      :model-value="accountGroupForm.enabled"
                      @update:model-value="accountGroupForm.enabled = Boolean($event)"
                    />
                    Enable group
                  </SurfaceBox>

                  <label class="block text-xs">
                    <span class="ui-field-label">Notes</span>
                    <textarea
                      v-model.trim="accountGroupForm.notes"
                      rows="3"
                      class="ui-textarea-sm"
                      placeholder="Example: route high-quota accounts through the Hong Kong proxy pool"
                    ></textarea>
                  </label>

                  <Button size="sm" variant="primary" root-class="w-full justify-center" :disabled="accountGroupSaving" @click="saveAccountGroup">
                    {{ accountGroupSaving ? 'Saving…' : editingAccountGroupId ? 'Save group' : 'Create group' }}
                  </Button>
                </div>
              </div>

              <div class="max-h-[32rem] overflow-y-auto p-4">
                <StateBlock v-if="accountGroupRows.length === 0" dashed>
                  No groups yet. Create one on the left, for example, High-quota accounts, Codex, or Manual tokens.
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
                            {{ group.enabled ? 'Enabled' : 'Disabled' }}
                          </StateBadge>
                        </div>
                        <p class="mt-1 text-xs text-muted-foreground">
                          {{ group.account_count }} accounts · Default proxy: {{ group.proxy_label }}
                        </p>
                        <p v-if="group.notes" class="mt-1 line-clamp-2 text-xs text-muted-foreground">{{ group.notes }}</p>
                      </div>

                      <div class="flex shrink-0 items-center gap-2">
                        <Button size="xs" variant="outline" :disabled="accountGroupSaving" @click="editAccountGroup(group.raw)">
                          Edit
                        </Button>
                        <Button size="xs" variant="outline" root-class="text-rose-600" :disabled="accountGroupSaving" @click="deleteAccountGroup(group.raw)">
                          Delete
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
      aria-label="Import accounts"
      :z-index="120"
    >
            <ModalHeader title="Import accounts" :close-disabled="importModalBusy" compact @close="closeImportModal" />

            <div class="grid grid-cols-1 gap-0 md:grid-cols-[15rem_1fr]">
              <div class="flex flex-col border-b border-border bg-muted/20 p-3 md:border-b-0 md:border-r">
                <div class="space-y-1">
                  <button
                    v-for="option in importModeOptions"
                    :key="option.value"
                    type="button"
                    class="min-h-10 w-full rounded-full px-4 py-2 text-left text-sm transition-colors"
                    :class="importMode === option.value ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-card hover:text-foreground'"
                    :disabled="importModalBusy"
                    @click="setImportMode(option.value)"
                  >
                    {{ option.label }}
                  </button>
                </div>
                <AccountImportTargetGroupField
                  v-model="importTargetGroupValue"
                  class="mt-3 border-t border-border pt-3"
                  :groups="accountGroups"
                  :loading="accountGroupsLoading"
                  :disabled="importModalBusy"
                />
              </div>

              <div class="min-h-[clamp(26rem,55vh,42rem)] p-4">
                <div v-if="importMode === 'oauth_login'" class="space-y-3">
                  <ImportModePanel
                    title="Sign in to an existing account with OAuth"
                    description="Sign in to ChatGPT in your browser, then paste the callback URL to save the RT. It can renew an AT before it expires."
                  />
                  <div class="grid grid-cols-1 gap-3">
                    <label class="block text-xs">
                      <span class="ui-field-label">Account email (optional)</span>
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
                        {{ oauthAuthorizeUrl ? 'Regenerate authorization link' : 'Generate and open authorization page' }}
                      </Button>
                      <Button v-if="oauthAuthorizeUrl" size="xs" variant="outline" :disabled="importBusy" @click="openOAuthAuthorizeUrl">
                        Open authorization page
                      </Button>
                      <Button v-if="oauthAuthorizeUrl" size="xs" variant="outline" :disabled="importBusy" @click="copyOAuthAuthorizeUrl">
                        Copy authorization link
                      </Button>
                    </div>

                    <SurfaceBox v-if="oauthAuthorizeUrl" tone="muted" density="compact" wrap>
                      Authorization link generated. After signing in, paste the final callback URL from your browser below.
                      <span v-if="oauthRedirectUriPrefix">Redirect URI: {{ oauthRedirectUriPrefix }}</span>
                    </SurfaceBox>

                    <label class="block text-xs">
                      <span class="ui-field-label">Callback URL / Code</span>
                      <textarea
                        v-model.trim="oauthCallbackText"
                        rows="5"
                        class="ui-textarea-sm font-mono"
                        placeholder="Paste the full callback URL or just the code"
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
                        {{ importBusy ? 'Importing…' : 'Finish import' }}
                      </Button>
                    </div>
                  </div>
                </div>

                <div v-else-if="importMode === 'access_token'" class="space-y-3">
                  <ImportModePanel
                    title="Import access tokens"
                    description="Paste tokens directly, one per line, or load a TXT file with one token per line."
                  />
                  <textarea
                    v-model.trim="manualTokenText"
                    rows="10"
                    class="ui-textarea-sm font-mono"
                    placeholder="One access token per line"
                  ></textarea>
                  <div class="flex flex-wrap justify-end gap-2">
                    <Button size="xs" variant="outline" :disabled="importBusy" @click="openManualTokenFile">
                      Load TXT file
                    </Button>
                    <Button size="xs" variant="primary" :disabled="importBusy || !manualTokenText.trim()" @click="importManualTokenText">
                      {{ importBusy ? 'Importing…' : 'Start import' }}
                    </Button>
                  </div>
                </div>

                <div v-else-if="importMode === 'session_json'" class="space-y-3">
                  <ImportModePanel title="Import session JSON">
                    <template #description>
                      <p class="mt-1 text-xs leading-6 text-muted-foreground">
                        Open
                        <a
                          href="https://chatgpt.com/api/auth/session"
                          target="_blank"
                          rel="noopener noreferrer"
                          class="font-medium text-primary underline decoration-primary/35 underline-offset-2 hover:decoration-primary"
                        >https://chatgpt.com/api/auth/session</a>, copy the full JSON, and paste it here. The importer keeps the AT, RT, and ID token; this endpoint usually does not include a long-lived RT.
                      </p>
                    </template>
                  </ImportModePanel>
                  <textarea v-model.trim="sessionJsonText" rows="12" class="ui-textarea-sm font-mono" placeholder="Paste the full session JSON"></textarea>
                  <div class="flex justify-end">
                    <Button size="xs" variant="primary" :disabled="importBusy || !sessionJsonText.trim()" @click="importSessionJson">
                      {{ importBusy ? 'Importing…' : 'Start import' }}
                    </Button>
                  </div>
                </div>

                <div v-else-if="importMode === 'backup_json'" class="space-y-3">
                  <ImportModePanel
                    title="Import full backup file"
                    description="Load a full account JSON export from this system to restore saved credentials and account settings. No remote verification is performed."
                  />
                  <StateBlock dashed compact>
                    <Button size="sm" variant="outline" :disabled="importBusy" @click="openAccountFileDialog">
                      Select backup JSON file
                    </Button>
                  </StateBlock>
                </div>

                <div v-else-if="importMode === 'cpa_json' || importMode === 'sub2api_json'" class="space-y-3">
                  <ImportModePanel
                    :title="importMode === 'sub2api_json' ? 'Import Sub2API JSON file' : 'Import CPA JSON file'"
                    :description="importMode === 'sub2api_json'
                      ? 'Load JSON files exported by Sub2API to extract account credentials and sync account details and quotas.'
                      : 'Extract account credentials from one or more CPA JSON files, then verify them remotely and sync account details and quotas.'"
                  />
                  <StateBlock dashed compact>
                    <Button size="sm" variant="outline" :disabled="importBusy" @click="openAccountFileDialog">
                      Select {{ importMode === 'sub2api_json' ? 'Sub2API' : 'CPA' }} JSON file(s)
                    </Button>
                  </StateBlock>
                </div>

                <div v-else-if="importMode === 'remote_cpa'" class="space-y-3">
                  <RemoteAccountImportPanel
                    mode="cpa"
                    external-tracking
                    :target-group-id="resolvedImportTargetGroupId"
                    @busy-change="remoteImportBusy = $event"
                    @progress="updateRemoteImportProgress"
                    @started="startRemoteImportTracking"
                  />
                </div>

                <div v-else-if="importMode === 'sub2api'" class="space-y-3">
                  <RemoteAccountImportPanel
                    mode="sub2api"
                    external-tracking
                    :target-group-id="resolvedImportTargetGroupId"
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
    <input ref="accountFileInputRef" type="file" accept=".json,application/json" multiple class="hidden" @change="handleAccountFileChange" />
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
import AccountImportTargetGroupField from './accounts/AccountImportTargetGroupField.vue'
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
  allMatchingSelected,
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
  importTargetGroupValue,
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
  selectAllMatching,
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
  importLocalAccountFiles,
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
const accountFileInputRef = ref<HTMLInputElement | null>(null)
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
const resolvedImportTargetGroupId = computed(() => (
  importTargetGroupValue.value === '__preserve__' ? null : importTargetGroupValue.value
))

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
  accountMatchingTotal: accountListTotal,
  allMatchingSelected,
  accountGroupsLoading,
  bindAccountGroupOptions,
  selectedBindGroupId,
  openCreateModal,
  openImportModal,
  exportAccounts,
  runBulkAction,
  bindSelectedAccountsToGroup,
  selectAllAccounts,
  selectAllMatching,
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

function openAccountFileDialog() {
  if (!accountFileInputRef.value || importBusy.value) return
  accountFileInputRef.value.value = ''
  accountFileInputRef.value.click()
}

async function handleAccountFileChange(event: Event) {
  const target = event.target as HTMLInputElement | null
  await importLocalAccountFiles(target?.files)
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
