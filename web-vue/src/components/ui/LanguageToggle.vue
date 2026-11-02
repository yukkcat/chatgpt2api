<template>
  <Tooltip :text="title" placement="bottom">
    <Button
      size="sm"
      variant="outline"
      data-i18n-skip
      :aria-label="title"
      @click="toggleUiLanguage"
    >
      <span :class="{ 'font-semibold text-foreground': uiLanguage === 'en', 'text-muted-foreground': uiLanguage !== 'en' }">EN</span>
      <span class="mx-1 text-muted-foreground">/</span>
      <span :class="{ 'font-semibold text-foreground': uiLanguage === 'zh', 'text-muted-foreground': uiLanguage !== 'zh' }">中文</span>
    </Button>
  </Tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button, Tooltip } from 'nanocat-ui'
import { toggleUiLanguage, uiLanguage } from '@/lib/i18n'

const title = computed(() => (uiLanguage.value === 'zh' ? 'Switch to English' : '切换到中文'))
</script>
