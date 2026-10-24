import { computed, reactive, ref } from 'vue'

import {
  proxyApi,
  type ProxyGroup,
  type ProxyNode,
  type ProxyNodeImportNode,
  type ProxyNodeImportResult,
  type ProxyTestResult,
} from '@/api/proxy'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useOperationProgressRuntime } from '@/composables/useOperationProgressRuntime'
import { useToast } from '@/composables/useToast'
import { errorMessage, prefixedErrorMessage } from '@/lib/errorMessage'
import {
  proxyGroupReference,
  proxyNodeTestClass,
  proxyNodeTestSummary,
} from '@/views/proxy/proxyView'

export type ProxyGroupNodeForm = {
  id: string
  name: string
  url: string
  enabled: boolean
  image_concurrency_limit: number
  notes: string
}

export type ProxyGroupForm = {
  id: string
  name: string
  enabled: boolean
  notes: string
  nodes: ProxyGroupNodeForm[]
}

export const FORM_TEST_KEY = '__form__'

const DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY = 30

function createGeneratedId(prefix: string) {
  let suffix = ''
  try {
    suffix = globalThis.crypto?.randomUUID?.().replace(/-/g, '').slice(0, 10) || ''
  } catch {
    suffix = ''
  }
  if (!suffix) {
    suffix = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`.slice(0, 10)
  }
  return `${prefix}-${suffix}`
}

export function cleanProxyGroupDraftId(value: string) {
  return String(value || '').trim()
}

export function normalizeImageConcurrencyLimit(value: unknown) {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return 0
  return Math.max(0, Math.min(10000, Math.floor(parsed)))
}

function createDefaultNode(index = 0): ProxyGroupNodeForm {
  return {
    id: createGeneratedId('node'),
    name: `Egress ${index + 1}`,
    url: '',
    enabled: true,
    image_concurrency_limit: DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY,
    notes: '',
  }
}

function createDefaultGroupForm(): ProxyGroupForm {
  return {
    id: '',
    name: '',
    enabled: true,
    notes: '',
    nodes: [createDefaultNode(0)],
  }
}

function normalizeGroupNode(item: ProxyGroupNodeForm | ProxyNode, index: number): ProxyGroupNodeForm {
  const id = cleanProxyGroupDraftId(item.id || '') || createGeneratedId('node')
  return {
    id,
    name: String(item.name || `Egress ${index + 1}`).trim(),
    url: String(item.url || '').trim(),
    enabled: item.enabled !== false,
    image_concurrency_limit: normalizeImageConcurrencyLimit(item.image_concurrency_limit ?? DEFAULT_PROXY_NODE_IMAGE_CONCURRENCY),
    notes: String(item.notes || '').trim(),
  }
}

function groupFormSignature(form: ProxyGroupForm) {
  return JSON.stringify({
    id: cleanProxyGroupDraftId(form.id),
    name: form.name.trim(),
    enabled: form.enabled !== false,
    notes: form.notes.trim(),
    nodes: form.nodes.map((node) => ({
      id: cleanProxyGroupDraftId(node.id),
      name: node.name.trim(),
      url: node.url.trim(),
      enabled: node.enabled !== false,
      image_concurrency_limit: normalizeImageConcurrencyLimit(node.image_concurrency_limit),
      notes: node.notes.trim(),
    })),
  })
}

export function mergeImportedProxyNodes(
  currentNodes: readonly ProxyGroupNodeForm[],
  nodes: readonly ProxyNodeImportNode[],
) {
  const retainedNodes = currentNodes.length === 1 && !currentNodes[0].url.trim()
    ? []
    : [...currentNodes]
  const importedNodes = nodes.map((node, index) => ({
    ...createDefaultNode(retainedNodes.length + index),
    url: node.url,
    image_concurrency_limit: node.image_concurrency_limit,
  }))
  return [...retainedNodes, ...importedNodes]
}

export function useProxyGroupRuntime() {
  const toast = useToast()
  const confirmDialog = useConfirmDialog()
  const progressRuntime = useOperationProgressRuntime()
  const operationProgress = progressRuntime.state
  const savingGroupId = ref('')
  const deletingGroupId = ref('')
  const testingKey = ref('')
  const groupKeyword = ref('')
  const showGroupModal = ref(false)
  const showNodeImportModal = ref(false)
  const closingGroupModal = ref(false)
  const editingGroupId = ref('')
  const groups = ref<ProxyGroup[]>([])
  const testResults = reactive<Record<string, ProxyTestResult>>({})
  const groupForm = reactive<ProxyGroupForm>(createDefaultGroupForm())
  const groupFormBaseline = ref(groupFormSignature(groupForm))
  const isGroupFormDirty = computed(() => (
    showGroupModal.value && groupFormSignature(groupForm) !== groupFormBaseline.value
  ))
  const groupNodeImportExistingUrls = computed(() => (
    groupForm.nodes.map((node) => node.url.trim()).filter(Boolean)
  ))

  const filteredGroups = computed(() => {
    const query = groupKeyword.value.trim().toLowerCase()
    const rows = [...groups.value].sort((left, right) => (
      (left.name || left.id).localeCompare(right.name || right.id, 'zh-Hans-CN')
    ))
    if (!query) return rows
    return rows.filter((item) => [
      item.id,
      item.name,
      item.notes,
      ...item.nodes.flatMap((node) => [node.id, node.name, node.url, node.notes]),
    ].some((value) => String(value || '').toLowerCase().includes(query)))
  })

  function updateGroups(items: ProxyGroup[]) {
    groups.value = Array.isArray(items) ? [...items] : []
  }

  function upsertGroup(item: ProxyGroup) {
    const index = groups.value.findIndex((group) => group.id === item.id)
    if (index < 0) {
      groups.value = [...groups.value, item]
      return
    }
    const next = [...groups.value]
    next[index] = item
    groups.value = next
  }

  async function copyText(value: string, message = 'Copied') {
    const text = String(value || '').trim()
    if (!text) return
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const input = document.createElement('textarea')
        input.value = text
        input.setAttribute('readonly', 'readonly')
        input.style.position = 'fixed'
        input.style.opacity = '0'
        document.body.appendChild(input)
        input.select()
        document.execCommand('copy')
        document.body.removeChild(input)
      }
      toast.success(message)
    } catch {
      toast.error('Copy failed')
    }
  }

  function copyProxyGroupReference(group: Pick<ProxyGroup, 'id' | 'reference_text'>) {
    void copyText(proxyGroupReference(group), 'Proxy group reference copied')
  }

  function resetGroupForm() {
    showNodeImportModal.value = false
    editingGroupId.value = ''
    Object.assign(groupForm, createDefaultGroupForm())
    groupFormBaseline.value = groupFormSignature(groupForm)
  }

  function openCreateGroupModal() {
    resetGroupForm()
    showGroupModal.value = true
  }

  function openEditGroupModal(group: ProxyGroup) {
    editingGroupId.value = group.id
    Object.assign(groupForm, {
      id: group.id,
      name: group.name || group.id,
      enabled: group.enabled !== false,
      notes: group.notes || '',
      nodes: group.nodes.length ? group.nodes.map((node, index) => normalizeGroupNode(node, index)) : [createDefaultNode(0)],
    })
    groupFormBaseline.value = groupFormSignature(groupForm)
    showGroupModal.value = true
  }

  function finishCloseGroupModal() {
    showGroupModal.value = false
    resetGroupForm()
  }

  async function closeGroupModal() {
    if (savingGroupId.value === FORM_TEST_KEY || closingGroupModal.value) return
    if (isGroupFormDirty.value) {
      closingGroupModal.value = true
      try {
        const confirmed = await confirmDialog.ask({
          title: 'Discard proxy group draft',
          message: 'This proxy group has unsaved changes. Closing it will discard them. Continue?',
          confirmText: 'Discard changes',
          cancelText: 'Continue editing',
        })
        if (!confirmed) return
      } finally {
        closingGroupModal.value = false
      }
    }
    finishCloseGroupModal()
  }

  function openNodeImportModal() {
    showNodeImportModal.value = true
  }

  function closeNodeImportModal() {
    showNodeImportModal.value = false
  }

  function addGroupNode() {
    groupForm.nodes.push(createDefaultNode(groupForm.nodes.length))
  }

  function removeGroupNode(index: number) {
    if (groupForm.nodes.length <= 1) {
      groupForm.nodes = [createDefaultNode(0)]
      return
    }
    groupForm.nodes.splice(index, 1)
  }

  function applyNodeImport(result: ProxyNodeImportResult) {
    if (result.nodes.length) {
      groupForm.nodes = mergeImportedProxyNodes(groupForm.nodes, result.nodes)
    }
  }

  async function saveProxyGroup() {
    const groupName = groupForm.name.trim()
    if (!groupName) {
      toast.warning('Enter a proxy group name')
      return
    }
    const id = cleanProxyGroupDraftId(editingGroupId.value || groupForm.id) || createGeneratedId('pg')
    const nodes = groupForm.nodes
      .map((node, index) => normalizeGroupNode(node, index))
      .filter((node) => node.url)
    if (!nodes.length) {
      toast.warning('Enter at least one proxy node address')
      return
    }
    savingGroupId.value = FORM_TEST_KEY
    try {
      const wasEditing = Boolean(editingGroupId.value)
      const response = await proxyApi.saveGroup({
        id,
        name: groupName,
        enabled: groupForm.enabled,
        notes: groupForm.notes.trim(),
        nodes,
        create_only: !editingGroupId.value,
      })
      upsertGroup(response.group)
      savingGroupId.value = ''
      finishCloseGroupModal()
      toast.success(wasEditing ? 'Proxy group updated' : 'Proxy group created')
    } catch (error) {
      toast.error(prefixedErrorMessage('Failed to save proxy group', error))
    } finally {
      savingGroupId.value = ''
    }
  }

  async function toggleProxyGroup(group: ProxyGroup) {
    const nextEnabled = !group.enabled
    const confirmed = await confirmDialog.ask({
      title: nextEnabled ? 'Confirm enabling proxy group' : 'Confirm disabling proxy group',
      message: `This will ${nextEnabled ? 'enable' : 'disable'} proxy group ${group.name || group.id}. Account groups assigned to it will be affected. Continue?`,
      confirmText: nextEnabled ? 'Enable' : 'Disable',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    savingGroupId.value = group.id
    try {
      const response = await proxyApi.saveGroup({
        id: group.id,
        enabled: nextEnabled,
      })
      upsertGroup(response.group)
      toast.success(`Proxy group ${group.name || group.id} ${group.enabled ? 'disabled' : 'enabled'}`)
    } catch (error) {
      toast.error(prefixedErrorMessage('Failed to change proxy group status', error))
    } finally {
      savingGroupId.value = ''
    }
  }

  async function deleteProxyGroup(group: ProxyGroup) {
    if (group.can_delete === false) return

    const confirmed = await confirmDialog.ask({
      title: 'Delete proxy group',
      message: `Delete proxy group ${group.name || group.id}? It is not currently referenced by any egress, account group, or account. This action cannot be undone.`,
      confirmText: 'Delete',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    deletingGroupId.value = group.id
    try {
      const response = await proxyApi.deleteGroup(group.id)
      groups.value = groups.value.filter((item) => item.id !== response.deleted_id)
      toast.success('Proxy group deleted')
    } catch (error) {
      toast.error(prefixedErrorMessage('Failed to delete proxy group', error))
    } finally {
      deletingGroupId.value = ''
    }
  }

  function handleProxyGroupAction(group: ProxyGroup, action: string) {
    if (action === 'test-all') void testProxyGroupAll(group)
    if (action === 'toggle-enabled') void toggleProxyGroup(group)
    if (action === 'delete') void deleteProxyGroup(group)
  }

  async function testProxyGroupNode(group: Pick<ProxyGroup, 'id' | 'name'>, node: ProxyGroupNodeForm | ProxyNode) {
    const value = node.url.trim()
    if (!value) {
      toast.warning(`${node.name || node.id}: Enter a proxy address first`)
      return
    }
    const groupLabel = group.name || (group.id === FORM_TEST_KEY ? 'Current draft' : group.id)
    const confirmed = await confirmDialog.ask({
      title: 'Confirm proxy node test',
      message: `This will send an external network test request through node ${node.name || node.id} in proxy group ${groupLabel}. Confirm that testing this connection is allowed.`,
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    const groupKey = group.id || FORM_TEST_KEY
    const key = `group:${groupKey}:${node.id}`
    testingKey.value = key
    try {
      const response = await proxyApi.testGroup({ url: value })
      const result = response.result || response.results?.[0]?.result
      if (result) testResults[key] = result
      if (result?.ok) toast.success(`Node test passed, latency ${result.latency_ms}ms`)
      else toast.warning(result?.error || 'Node test failed')
    } catch (error) {
      const message = errorMessage(error, 'Node test failed')
      testResults[key] = {
        ok: false,
        status: 0,
        latency_ms: 0,
        error: message,
      }
      toast.error(message)
    } finally {
      testingKey.value = ''
    }
  }

  async function testProxyGroupAll(group: ProxyGroup) {
    const confirmed = await confirmDialog.ask({
      title: 'Confirm proxy group test',
      message: `This will test all ${group.nodes.length} nodes in proxy group ${group.name || group.id}. Each node will send an external network test request. Continue?`,
      confirmText: 'Start test',
      cancelText: 'Cancel',
    })
    if (!confirmed) return

    const key = `group:${group.id}:all`
    testingKey.value = key
    await progressRuntime.start({
      title: 'Test proxy group nodes',
      subtitle: group.name || group.id,
      total: group.nodes.length,
      message: `Testing ${group.nodes.length} nodes...`,
    })
    try {
      const response = await proxyApi.testGroup({ id: group.id })
      const results = response.results || []
      for (const item of results) {
        if (item.node_id && item.result) {
          testResults[`group:${group.id}:${item.node_id}`] = item.result
        }
      }
      if (response.summary.tone === 'success') {
        progressRuntime.succeed(response.summary.message, response.summary.total)
      } else if (response.summary.tone === 'warning') {
        progressRuntime.warn(response.summary.message, response.summary.total)
      } else {
        progressRuntime.fail(response.summary.message, response.summary.total)
      }
    } catch (error) {
      progressRuntime.fail(errorMessage(error, 'Proxy group test failed'))
    } finally {
      testingKey.value = ''
    }
  }

  function nodeTestSummary(group: ProxyGroup, node: ProxyNode) {
    return proxyNodeTestSummary(group, node, testResults, testingKey.value)
  }

  function nodeTestClass(group: ProxyGroup, node: ProxyNode) {
    return proxyNodeTestClass(group, node, testResults, testingKey.value)
  }

  return {
    savingGroupId,
    deletingGroupId,
    testingKey,
    operationProgress,
    closeOperationProgress: progressRuntime.close,
    groupKeyword,
    showGroupModal,
    showNodeImportModal,
    closingGroupModal,
    editingGroupId,
    groups,
    groupForm,
    groupNodeImportExistingUrls,
    filteredGroups,
    updateGroups,
    copyProxyGroupReference,
    openCreateGroupModal,
    openEditGroupModal,
    closeGroupModal,
    openNodeImportModal,
    closeNodeImportModal,
    addGroupNode,
    removeGroupNode,
    applyNodeImport,
    saveProxyGroup,
    handleProxyGroupAction,
    testProxyGroupNode,
    nodeTestSummary,
    nodeTestClass,
  }
}
