<template>
  <section class="metric-strip" :class="columnsClass">
    <article
      v-for="item in items"
      :key="item.key || item.label"
      class="metric-strip-card"
      :class="[
        density === 'compact' ? 'metric-strip-card--compact' : '',
        hasIcon(item) ? `metric-strip-card--icon-${iconPlacement}` : '',
        item.cardClass || '',
      ]"
    >
      <div
        class="metric-strip-card-body"
        :class="hasIcon(item) && iconPlacement === 'right' ? 'metric-strip-card-body--right-icon' : ''"
      >
        <span
          v-if="hasIcon(item)"
          class="metric-strip-icon"
          :class="[item.iconBgClass || item.iconBg || '', item.iconClass || item.iconColor || '']"
        >
          <svg
            v-if="isSvgPathIcon(item)"
            aria-hidden="true"
            viewBox="0 0 24 24"
            class="metric-strip-svg"
            fill="currentColor"
          >
            <path :d="item.svgPath || item.icon" />
          </svg>
          <Icon
            v-else-if="item.icon"
            aria-hidden="true"
            :icon="item.icon"
            class="metric-strip-svg"
          />
        </span>

        <span class="metric-strip-text">
          <span class="metric-strip-label">{{ item.label }}</span>
          <strong
            class="metric-strip-value"
            :class="item.valueClass || item.class || ''"
            :style="item.valueStyle || undefined"
          >
            {{ item.value }}
          </strong>
          <span v-if="item.meta" class="metric-strip-meta">{{ item.meta }}</span>
        </span>
      </div>
    </article>
  </section>
</template>

<script setup lang="ts">
import { Icon } from '@iconify/vue'

type MetricStripItem = {
  key?: string
  label: string
  value: string | number
  meta?: string
  class?: string
  valueClass?: string
  valueStyle?: Record<string, string>
  cardClass?: string
  icon?: string
  iconType?: 'iconify' | 'svgPath'
  svgPath?: string
  iconClass?: string
  iconColor?: string
  iconBg?: string
  iconBgClass?: string
}

withDefaults(defineProps<{
  items: MetricStripItem[]
  columnsClass?: string
  density?: 'normal' | 'compact'
  iconPlacement?: 'left' | 'right'
}>(), {
  columnsClass: 'grid-cols-2 md:grid-cols-3 xl:grid-cols-4',
  density: 'normal',
  iconPlacement: 'left',
})

function hasIcon(item: MetricStripItem) {
  return Boolean(item.icon || item.svgPath)
}

function isSvgPathIcon(item: MetricStripItem) {
  if (item.iconType === 'svgPath' || item.svgPath) return true
  return Boolean(item.icon && !item.icon.includes(':'))
}
</script>

<style scoped>
.metric-strip {
  display: grid;
  gap: 12px;
}

.metric-strip-card {
  position: relative;
  min-width: 0;
  min-height: 76px;
  padding: 16px;
  border: 1px solid hsl(var(--border) / 0.82);
  border-radius: 16px;
  background: hsl(var(--card));
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.metric-strip-card--compact {
  min-height: 64px;
  padding: 10px 12px;
  border-radius: 16px;
}

.metric-strip-card-body {
  display: flex;
  min-width: 0;
  height: 100%;
  align-items: center;
  gap: 12px;
}

.metric-strip-card-body--right-icon {
  display: block;
  height: auto;
  padding-right: 48px;
}

.metric-strip-icon {
  display: inline-flex;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
}

.metric-strip-card--compact .metric-strip-icon {
  width: 30px;
  height: 30px;
  border-radius: 10px;
}

.metric-strip-card--icon-right .metric-strip-icon {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border-radius: 999px;
}

.metric-strip-card--compact.metric-strip-card--icon-right .metric-strip-icon {
  top: 10px;
  right: 12px;
  width: 32px;
  height: 32px;
}

.metric-strip-card--compact .metric-strip-card-body--right-icon {
  padding-right: 40px;
}

.metric-strip-card--icon-left .metric-strip-icon:not([class*='bg-']) {
  background: hsl(var(--secondary));
}

.metric-strip-svg {
  width: 18px;
  height: 18px;
}

.metric-strip-card--compact .metric-strip-svg {
  width: 16px;
  height: 16px;
}

.metric-strip-text {
  display: block;
  min-width: 0;
  line-height: 1.2;
}

.metric-strip-label {
  display: block;
  overflow: hidden;
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-strip-value {
  display: block;
  overflow: hidden;
  margin-top: 5px;
  font-size: 18px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-strip-card:not(.metric-strip-card--compact) .metric-strip-value {
  margin-top: 8px;
  font-size: 24px;
}

.metric-strip-meta {
  display: block;
  overflow: hidden;
  margin-top: 4px;
  color: hsl(var(--muted-foreground));
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 640px) {
  .metric-strip-card {
    min-height: 62px;
  }
}
</style>
