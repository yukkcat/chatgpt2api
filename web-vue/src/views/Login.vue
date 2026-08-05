<template>
  <div class="min-h-screen px-4">
    <div class="flex min-h-screen items-center justify-center">
      <div class="w-full max-w-md rounded-[2.5rem] border border-border bg-card p-10 shadow-2xl shadow-black/10">
        <div class="text-center">
          <h1 class="text-3xl font-semibold text-foreground">ChatGPT2API</h1>
          <p class="mt-2 text-sm text-muted-foreground">控制台登录</p>
        </div>

        <form class="mt-8 space-y-6" @submit.prevent="handleLogin">
          <div class="space-y-2">
            <label for="password" class="ui-field-label text-sm font-medium text-foreground">
              管理密钥
            </label>
            <Input
              id="password"
              v-model="password"
              type="password"
              size="md"
              block
              placeholder="输入 Bearer key"
              :disabled="isLoading"
            />
          </div>

          <Button
            type="submit"
            size="md"
            variant="primary"
            block
            :disabled="isLoading || !password"
          >
            {{ isLoading ? '登录中...' : '登录' }}
          </Button>
        </form>

        <div class="mt-8 flex items-center justify-center gap-4 text-xs text-muted-foreground">
          <a
            href="https://github.com/yukkcat/chatgpt2api"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-2 transition-colors hover:text-foreground"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" class="h-4 w-4" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.477 2 12c0 4.419 2.865 8.166 6.839 9.489.5.09.682-.217.682-.483 0-.237-.009-.868-.014-1.703-2.782.604-3.369-1.341-3.369-1.341-.454-1.154-1.11-1.462-1.11-1.462-.908-.62.069-.608.069-.608 1.004.071 1.532 1.031 1.532 1.031.892 1.529 2.341 1.087 2.91.832.091-.647.349-1.087.636-1.337-2.22-.253-4.555-1.11-4.555-4.944 0-1.092.39-1.987 1.029-2.687-.103-.253-.446-1.272.098-2.65 0 0 .84-.269 2.75 1.026A9.564 9.564 0 0 1 12 6.844c.85.004 1.705.115 2.504.337 1.909-1.295 2.748-1.026 2.748-1.026.546 1.378.202 2.397.1 2.65.64.7 1.028 1.595 1.028 2.687 0 3.842-2.338 4.687-4.566 4.936.359.309.678.919.678 1.852 0 1.337-.012 2.418-.012 2.747 0 .268.18.577.688.479A10.002 10.002 0 0 0 22 12c0-5.523-4.477-10-10-10z" />
            </svg>
            GitHub
          </a>
          <span>Powered by ChatGPT2API</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, Input } from 'nanocat-ui'
import { useToast } from '@/composables/useToast'
import { resolveLoginRedirect } from '@/router/routes'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const toast = useToast()

const password = ref('')
const isLoading = ref(false)

async function handleLogin() {
  if (!password.value) return

  isLoading.value = true

  try {
    const loggedIn = await authStore.login(password.value)
    if (!loggedIn) {
      toast.error('密钥无效或已失效。')
      return
    }
    await router.replace(resolveLoginRedirect(route.query.redirect, authStore.homeRoute))
  } catch (error: any) {
    toast.error(error.message || '登录失败，请检查密码。')
  } finally {
    isLoading.value = false
  }
}
</script>
