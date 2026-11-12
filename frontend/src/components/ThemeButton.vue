<script setup>
import { Moon, Sun } from 'lucide-vue-next'
import { theme, toggleTheme } from '../session'
defineProps({ label: Boolean })
</script>

<template>
  <button class="button subtle" type="button" :aria-label="theme === 'dark' ? '切换亮色' : '切换暗色'" @click="toggleTheme">
    <Sun v-if="theme === 'dark'" :size="17" /><Moon v-else :size="17" />
    <span v-if="label">{{ theme === 'dark' ? '亮色模式' : '暗色模式' }}</span>
  </button>
</template>
