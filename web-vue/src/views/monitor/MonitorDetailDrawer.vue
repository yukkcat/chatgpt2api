<template>
  <RequestDetailDrawer
    :open="open"
    title="请求详情"
    :loading="loading"
    :error="error"
    max-width="clamp(22rem, 30vw, 32rem)"
    root-class="monitor-call-detail-drawer"
    detached
    loading-title="正在读取请求详情"
    loading-description="正在整理阶段时间线..."
    error-title="请求详情加载失败"
    @close="emit('close')"
  >
    <template v-if="record">
      <section class="monitor-call-detail__summary">
        <div class="min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <StateBadge :tone="record.presentation.status_tone" shape="rounded">
              {{ record.presentation.status_label }}
            </StateBadge>
            <MetaChip size="xs" tone="muted">{{ record.model || '-' }}</MetaChip>
          </div>
          <p class="mt-3 break-all font-mono text-xs text-muted-foreground">{{ record.call_id }}</p>
          <p class="mt-1 text-xs text-muted-foreground">{{ record.endpoint || '-' }}</p>
        </div>
        <div class="monitor-call-detail__duration">
          <span>总耗时</span>
          <strong>{{ record.presentation.duration_text }}</strong>
        </div>
      </section>

      <section class="monitor-call-detail__facts">
        <div>
          <span>账号</span>
          <strong>{{ record.account_email || '-' }}</strong>
        </div>
        <div>
          <span>出口</span>
          <strong>{{ record.presentation.egress_text }}</strong>
        </div>
        <div>
          <span>账号尝试</span>
          <strong>{{ record.presentation.account_attempt_text || '-' }}</strong>
        </div>
        <div>
          <span>关键耗时</span>
          <strong>{{ record.presentation.metric_digest }}</strong>
        </div>
      </section>

      <section>
        <div class="monitor-call-detail__section-title">
          <span>阶段时间线</span>
          <MetaChip size="xs" tone="muted">{{ events.length }} 个阶段</MetaChip>
        </div>
        <ol v-if="events.length" class="monitor-call-timeline">
          <li v-for="(event, index) in events" :key="`${event.event}-${event.time}-${index}`">
            <span class="monitor-call-timeline__dot" />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <strong>{{ event.label || event.event }}</strong>
                <time>{{ event.time || '-' }}</time>
              </div>
              <p v-if="event.timing_text && event.timing_text !== '-'">{{ event.timing_text }}</p>
                <p v-if="event.detail_text" class="text-foreground">{{ event.detail_text }}</p>
            </div>
          </li>
        </ol>
        <EmptyState v-else plain title="暂无阶段记录" description="该请求没有保留可展示的阶段事件。" />
      </section>

      <StateBlock
        v-if="record.presentation.error_text"
        title="失败原因"
        :description="record.presentation.error_text"
        compact
      />
    </template>
  </RequestDetailDrawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { EmptyState } from 'nanocat-ui'

import type { RealtimeMonitorRecordDetail } from '@/api/monitor'
import MetaChip from '@/components/ai/MetaChip.vue'
import RequestDetailDrawer from '@/components/ai/RequestDetailDrawer.vue'
import StateBadge from '@/components/ai/StateBadge.vue'
import StateBlock from '@/components/ai/StateBlock.vue'

const props = defineProps<{
  open: boolean
  record: RealtimeMonitorRecordDetail | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const events = computed(() => props.record?.events || [])
</script>

<style scoped>
:global(.ui-modal-panel.monitor-call-detail-drawer) {
  height: 90dvh;
  max-height: 90dvh;
}

.monitor-call-detail__summary {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid hsl(var(--border));
  padding-bottom: 16px;
}

.monitor-call-detail__duration {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  text-align: right;
}

.monitor-call-detail__duration span,
.monitor-call-detail__facts span,
.monitor-call-timeline time,
.monitor-call-timeline p {
  color: hsl(var(--muted-foreground));
  font-size: 11px;
}

.monitor-call-detail__duration strong {
  color: hsl(var(--foreground));
  font-size: 20px;
}

.monitor-call-detail__facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.monitor-call-detail__facts > div {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 5px;
  border-radius: 12px;
  background: hsl(var(--muted) / 0.34);
  padding: 10px 12px;
}

.monitor-call-detail__facts strong {
  overflow-wrap: anywhere;
  color: hsl(var(--foreground));
  font-size: 12px;
  font-weight: 600;
}

.monitor-call-detail__section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  color: hsl(var(--foreground));
  font-size: 13px;
  font-weight: 600;
}

.monitor-call-timeline {
  margin: 0;
  padding: 0;
  list-style: none;
}

.monitor-call-timeline li {
  position: relative;
  display: flex;
  gap: 12px;
  padding: 0 0 16px;
}

.monitor-call-timeline li:not(:last-child)::before {
  position: absolute;
  top: 12px;
  bottom: -2px;
  left: 4px;
  width: 1px;
  background: hsl(var(--border));
  content: '';
}

.monitor-call-timeline__dot {
  position: relative;
  z-index: 1;
  width: 9px;
  height: 9px;
  flex: 0 0 auto;
  margin-top: 5px;
  border: 2px solid hsl(var(--background));
  border-radius: 9999px;
  background: hsl(var(--primary));
  box-shadow: 0 0 0 1px hsl(var(--primary) / 0.35);
}

.monitor-call-timeline strong {
  color: hsl(var(--foreground));
  font-size: 12px;
}

.monitor-call-timeline p {
  margin-top: 4px;
  overflow-wrap: anywhere;
  line-height: 1.5;
}

@media (max-width: 640px) {
  :global(.ui-modal-panel.monitor-call-detail-drawer) {
    height: calc(100dvh - 1rem);
    max-height: calc(100dvh - 1rem);
  }

  .monitor-call-detail__summary {
    flex-direction: column;
  }

  .monitor-call-detail__duration {
    align-items: flex-start;
    text-align: left;
  }

  .monitor-call-detail__facts {
    grid-template-columns: 1fr;
  }
}
</style>
