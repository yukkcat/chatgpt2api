<template>
  <section class="attempt-timeline">
    <button
      type="button"
      class="attempt-timeline__header"
      :aria-expanded="attemptsVisible"
      @click="attemptsVisible = !attemptsVisible"
    >
      <div class="attempt-timeline__heading">
        <span class="attempt-timeline__title">
          <Icon icon="lucide:repeat-2" />
          生成尝试
        </span>
      </div>
      <div class="attempt-timeline__summary">
        <MetaChip v-if="resultRequestedCount" size="xs" tone="muted">
          {{ resultRequestedCount }} 张 · 成功 {{ resultSucceededCount }} · 失败 {{ resultFailedCount }}
        </MetaChip>
        <MetaChip size="xs" tone="muted">{{ attemptRows.length }} 次尝试</MetaChip>
        <MetaChip v-if="displaySwitchCount" size="xs" tone="warning">
          切换 {{ displaySwitchCount }} 次
        </MetaChip>
        <span class="attempt-timeline__toggle-label">
          {{ attemptsVisible ? '收起' : '展开' }}
          <Icon
            icon="lucide:chevron-down"
            :class="{ 'attempt-timeline__chevron--open': attemptsVisible }"
          />
        </span>
      </div>
    </button>

    <div v-show="attemptsVisible" class="attempt-timeline__list">
      <section
        v-for="group in attemptGroups"
        :key="group.slot"
        class="attempt-timeline__group"
      >
        <div v-if="attemptGroups.length > 1" class="attempt-timeline__group-header">
          <strong>{{ group.slot_label }}</strong>
          <div>
            <span :class="`attempt-timeline__group-${group.status.tone}`">
              {{ group.status.label }}
            </span>
            <span>{{ group.attempt_text }}</span>
            <span v-if="group.switch_text">{{ group.switch_text }}</span>
          </div>
        </div>

        <div
          v-for="(attempt, index) in group.attempts"
          :key="attempt.key"
          class="attempt-timeline__item"
        >
          <div
            class="attempt-timeline__rail"
            :class="{ 'attempt-timeline__rail--last': index === group.attempts.length - 1 }"
          >
            <span :class="`attempt-timeline__marker--${attempt.presentation.marker_tone}`">
              <Icon :icon="attempt.presentation.marker_tone === 'success' ? 'lucide:check' : 'lucide:x'" />
            </span>
          </div>

          <div class="attempt-timeline__content">
            <div class="attempt-timeline__row">
              <div class="attempt-timeline__identity">
                <div class="attempt-timeline__attempt-label">
                  <strong>尝试 {{ attempt.attempt }}</strong>
                  <span v-if="attempt.presentation.switch_label" class="attempt-timeline__switch">
                    <Icon icon="lucide:repeat-2" />
                    {{ attempt.presentation.switch_label }}
                  </span>
                </div>
                <span class="attempt-timeline__account" :title="attempt.accountEmail">
                  <Icon icon="lucide:user-round" />
                  {{ attempt.accountEmail || '账号未记录' }}
                </span>
              </div>
              <div class="attempt-timeline__result">
                <RequestTimelineSummary
                  :step-count="attempt.timelineSummary.stepCount"
                  :duration-ms="attempt.durationMs"
                  :status="attempt.presentation.status"
                />
              </div>
            </div>

            <div v-if="attempt.presentation.show_failure" class="attempt-timeline__facts">
              <span class="attempt-timeline__fact">
                <Icon icon="lucide:circle-alert" />
                <span class="attempt-timeline__failure-message">
                  {{ attempt.presentation.failure_label }}
                </span>
                <code v-if="attempt.presentation.error_code_text" :title="attempt.presentation.error_code_text">
                  {{ attempt.presentation.error_code_text }}
                </code>
                <code v-if="attempt.presentation.status_code_text">
                  {{ attempt.presentation.status_code_text }}
                </code>
              </span>
              <details
                v-if="attempt.presentation.show_error_details"
                class="attempt-timeline__error-details"
              >
                <summary>
                  <span>错误详情</span>
                  <Icon icon="lucide:chevron-down" />
                </summary>
                <div class="attempt-timeline__error-content">
                  <div v-if="attempt.publicError" class="attempt-timeline__raw-error">
                    <span>对外错误</span>
                    <code>{{ attempt.publicError }}</code>
                  </div>
                  <div
                    v-if="attempt.upstreamError"
                    class="attempt-timeline__raw-error"
                  >
                    <span>上游错误</span>
                    <code>{{ attempt.upstreamError }}</code>
                  </div>
                  <div
                    v-if="attempt.upstreamText"
                    class="attempt-timeline__raw-error"
                  >
                    <span>上游文本</span>
                    <code>{{ attempt.upstreamText }}</code>
                  </div>
                </div>
              </details>
            </div>

            <div class="attempt-timeline__breakdown">
              <div
                v-if="attempt.timelineSegments.length || attempt.timelineGroups.length"
                class="attempt-timeline__breakdown-header"
              >
                <span>步骤耗时</span>
              </div>
              <RequestTimelineBreakdown
                :segments="attempt.timelineSegments"
                :legend-items="attempt.legendItems"
                :groups="attempt.timelineGroups"
                :details-visible="isAttemptDetailsVisible(attempt.key)"
                empty-message="这次尝试没有步骤耗时记录。"
                @toggle-details="toggleAttemptDetails(attempt.key)"
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { type AttemptGroupPresentation, type ImageAttempt } from '@/api/logs'
import MetaChip from '@/components/ai/MetaChip.vue'
import { buildTimelineView } from '@/views/logs/logDetailView'
import RequestTimelineBreakdown from '@/views/logs/RequestTimelineBreakdown.vue'
import RequestTimelineSummary from '@/views/logs/RequestTimelineSummary.vue'

const props = defineProps<{
  attempts: ImageAttempt[]
  groups: AttemptGroupPresentation[]
  requestedCount?: number
  succeededCount?: number
  failedCount?: number
  switchCount?: number
}>()

const attemptsVisible = ref(true)
const visibleAttemptDetails = ref<string[]>([])
const attemptRows = computed(() => props.attempts.map((attempt) => {
  const timeline = buildTimelineView(attempt.presentation.timeline)

  return {
    ...attempt,
    key: attemptKey(attempt),
    timelineSegments: timeline.segments,
    timelineGroups: timeline.groups,
    legendItems: timeline.legendItems,
    timelineSummary: timeline,
  }
}))
const attemptGroups = computed(() => {
  const groups = new Map<number, typeof attemptRows.value>()
  attemptRows.value.forEach((attempt) => {
    const attempts = groups.get(attempt.slot) || []
    attempts.push(attempt)
    groups.set(attempt.slot, attempts)
  })
  return props.groups.map((group) => ({
    ...group,
    attempts: groups.get(group.slot) || [],
  }))
})
const resultRequestedCount = computed(() => props.requestedCount || 0)
const resultSucceededCount = computed(() => props.succeededCount || 0)
const resultFailedCount = computed(() => props.failedCount || 0)
const displaySwitchCount = computed(() => props.switchCount || 0)

function attemptKey(attempt: ImageAttempt): string {
  return `${attempt.slot}-${attempt.attempt}-${attempt.accountEmail}`
}

function isAttemptDetailsVisible(key: string): boolean {
  return visibleAttemptDetails.value.includes(key)
}

function toggleAttemptDetails(key: string): void {
  visibleAttemptDetails.value = isAttemptDetailsVisible(key)
    ? visibleAttemptDetails.value.filter((item) => item !== key)
    : [...visibleAttemptDetails.value, key]
}

</script>

<style scoped>
.attempt-timeline {
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
  overflow: hidden;
}

.attempt-timeline__header,
.attempt-timeline__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.attempt-timeline__header {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 12px 14px;
  text-align: left;
  color: inherit;
}

.attempt-timeline__header:hover {
  background: hsl(var(--muted) / 0.22);
}

.attempt-timeline__heading {
  min-width: 0;
}

.attempt-timeline__title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 13px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.attempt-timeline__title svg {
  width: 14px;
  height: 14px;
  color: rgb(180 83 9);
}

.attempt-timeline__summary,
.attempt-timeline__facts,
.attempt-timeline__result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.attempt-timeline__summary {
  flex: 0 0 auto;
  justify-content: flex-end;
}

.attempt-timeline__toggle-label {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 2px;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__toggle-label svg {
  width: 14px;
  height: 14px;
  transition: transform 160ms ease;
}

.attempt-timeline__chevron--open {
  transform: rotate(180deg);
}

.attempt-timeline__list {
  border-top: 1px solid hsl(var(--border));
  padding: 0 14px 2px;
}

.attempt-timeline__group + .attempt-timeline__group {
  border-top: 1px solid hsl(var(--border));
}

.attempt-timeline__group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0 2px;
}

.attempt-timeline__group-header strong {
  font-size: 12px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.attempt-timeline__group-header div {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__group-success {
  color: rgb(22 163 74);
}

.attempt-timeline__group-danger {
  color: rgb(225 29 72);
}

.attempt-timeline__group-warning {
  color: rgb(180 83 9);
}

.attempt-timeline__group-muted {
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__item {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  gap: 10px;
}

.attempt-timeline__rail {
  position: relative;
  display: flex;
  justify-content: center;
  padding-top: 12px;
}

.attempt-timeline__rail::after {
  position: absolute;
  top: 32px;
  bottom: -1px;
  width: 1px;
  background: hsl(var(--border));
  content: '';
}

.attempt-timeline__rail--last::after {
  display: none;
}

.attempt-timeline__rail span {
  z-index: 1;
  display: grid;
  width: 20px;
  height: 20px;
  place-items: center;
  border-radius: 999px;
  color: white;
}

.attempt-timeline__rail svg {
  width: 12px;
  height: 12px;
}

.attempt-timeline__marker--success {
  background: rgb(22 163 74);
}

.attempt-timeline__marker--danger {
  background: rgb(225 29 72);
}

.attempt-timeline__content {
  min-width: 0;
  padding: 12px 0 14px;
}

.attempt-timeline__item + .attempt-timeline__item .attempt-timeline__content {
  border-top: 1px solid hsl(var(--border) / 0.7);
}

.attempt-timeline__identity {
  min-width: 0;
}

.attempt-timeline__attempt-label,
.attempt-timeline__account,
.attempt-timeline__switch {
  display: flex;
  align-items: center;
}

.attempt-timeline__attempt-label {
  flex-wrap: wrap;
  gap: 5px 8px;
}

.attempt-timeline__attempt-label strong {
  font-size: 12px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.attempt-timeline__switch {
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: rgb(180 83 9);
}

.attempt-timeline__switch svg {
  width: 12px;
  height: 12px;
}

.attempt-timeline__account {
  min-width: 0;
  gap: 5px;
  margin-top: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  overflow-wrap: anywhere;
}

.attempt-timeline__account svg {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
}

.attempt-timeline__result {
  flex: 0 0 auto;
  justify-content: flex-end;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__facts {
  display: grid;
  margin-top: 8px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__fact {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  line-height: 1.45;
}

.attempt-timeline__error-details {
  margin-left: 17px;
}

.attempt-timeline__error-details summary {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: fit-content;
  cursor: pointer;
  color: hsl(var(--muted-foreground));
  font-weight: 600;
  list-style: none;
}

.attempt-timeline__error-details summary::-webkit-details-marker {
  display: none;
}

.attempt-timeline__error-details summary svg {
  width: 12px;
  height: 12px;
  transition: transform 160ms ease;
}

.attempt-timeline__error-details[open] summary svg {
  transform: rotate(180deg);
}

.attempt-timeline__error-content {
  display: grid;
  gap: 7px;
  margin-top: 6px;
  border-left: 2px solid hsl(var(--border));
  padding-left: 9px;
}

.attempt-timeline__raw-error > span {
  display: block;
  margin-bottom: 3px;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__raw-error code {
  display: block;
  white-space: pre-wrap;
}

.attempt-timeline__fact > svg {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
  color: rgb(225 29 72);
}

.attempt-timeline__failure-message {
  font-weight: 600;
  color: rgb(190 18 60);
}

.attempt-timeline__facts code {
  font-size: 10px;
  overflow-wrap: anywhere;
  color: hsl(var(--muted-foreground));
}

.attempt-timeline__breakdown {
  margin-top: 11px;
  border-top: 1px dashed hsl(var(--border));
  padding-top: 10px;
}

.attempt-timeline__breakdown-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.attempt-timeline__breakdown-header > span {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 650;
  color: hsl(var(--foreground));
}

@media (max-width: 640px) {
  .attempt-timeline__header {
    flex-direction: column;
  }

  .attempt-timeline__summary {
    justify-content: flex-start;
  }

  .attempt-timeline__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
  }

  .attempt-timeline__identity {
    display: contents;
  }

  .attempt-timeline__attempt-label {
    grid-column: 1;
    grid-row: 1;
  }

  .attempt-timeline__account {
    grid-column: 1 / -1;
    grid-row: 2;
    margin-top: 0;
  }

  .attempt-timeline__result {
    grid-column: 2;
    grid-row: 1;
    flex-direction: column-reverse;
    align-items: flex-end;
  }

  .attempt-timeline__breakdown-header {
    align-items: flex-start;
    flex-direction: column;
  }

}
</style>
