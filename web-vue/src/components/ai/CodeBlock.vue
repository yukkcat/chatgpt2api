<template>
  <pre class="code-block scrollbar-slim"><code>{{ content }}</code></pre>
</template>

<script setup lang="ts">
defineProps<{
  content: string
}>()
</script>

<style scoped>
.code-block {
  margin-top: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  border: 1px solid hsl(var(--border));
  border-radius: 16px;
  background: hsl(var(--card));
  padding: 12px 16px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.55;
}
</style>
