<script setup>
import { nextTick, ref, watch } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps({ open: Boolean, title: String, wide: Boolean })
const emit = defineEmits(['close'])
const dialog = ref(null)
watch(() => props.open, async (open) => {
  await nextTick()
  if (open && !dialog.value.open) dialog.value.showModal()
  if (!open && dialog.value.open) dialog.value.close()
}, { immediate: true })
</script>

<template>
  <dialog ref="dialog" :class="{ 'dialog-wide': wide }" :aria-label="title" @cancel.prevent="emit('close')">
    <header class="dialog-header"><h2>{{ title }}</h2><button class="button subtle icon-only" aria-label="关闭" @click="emit('close')"><X :size="19" /></button></header>
    <div class="dialog-content"><slot v-if="open" /></div>
  </dialog>
</template>
