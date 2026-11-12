<script setup>
import { Inbox } from 'lucide-vue-next'
defineProps({ title: String, detail: String })
</script>

<template>
  <div class="empty-state"><span class="icon-box"><Inbox :size="21" /></span><h3>{{ title }}</h3><p v-if="detail">{{ detail }}</p><slot /></div>
</template>
