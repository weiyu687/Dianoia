<script setup>
import { computed, ref } from 'vue'
import { ArrowRight, LockKeyhole } from 'lucide-vue-next'
import { signIn } from '../session'
import Brand from './Brand.vue'
import ThemeButton from './ThemeButton.vue'

const props = defineProps({
  role: { type: String, required: true },
  sessionError: { type: String, default: '' },
})
const emit = defineEmits(['retry'])
const portal = computed(() => props.role === 'admin' ? '学校管理' : '教师工作台')
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function login() {
  loading.value = true
  error.value = ''
  try {
    await signIn({ username: username.value, password: password.value, role: props.role })
    password.value = ''
  } catch (failure) {
    error.value = failure.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-shell">
    <header class="login-top"><Brand :subtitle="portal" /><ThemeButton /></header>
    <div class="login-grid">
      <div class="login-art" aria-hidden="true"><div class="art-orbit orbit-a"></div><div class="art-orbit orbit-b"></div><div class="art-orbit orbit-c"></div></div>
      <main class="login-panel">
        <span class="icon-box"><LockKeyhole :size="20" /></span>
        <h1>{{ portal }}登录</h1>
        <div v-if="sessionError" class="error">
          <p role="alert">登录状态检查失败。{{ sessionError }}</p>
          <button class="button secondary" type="button" :disabled="loading" @click="emit('retry')">重新检查</button>
        </div>
        <form class="stack" @submit.prevent="login">
          <label>账号<input v-model.trim="username" autocomplete="username" maxlength="64" required placeholder="输入学校账号"></label>
          <label>密码<input v-model="password" type="password" autocomplete="current-password" maxlength="256" required placeholder="输入密码"></label>
          <p v-if="error" role="alert" class="error">{{ error }}</p>
          <button class="button primary" type="submit" :disabled="loading">{{ loading ? '正在登录' : '登录' }}<ArrowRight :size="17" /></button>
        </form>
      </main>
    </div>
  </div>
</template>
