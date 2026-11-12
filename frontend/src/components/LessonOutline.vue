<script setup>
import { ChevronDown, FileText } from 'lucide-vue-next'
defineProps({ sections: Array, active: String })
const emit = defineEmits(['select'])
</script>

<template>
  <ul class="outline-tree lesson-tree">
    <li v-for="section in sections" :key="section.id">
      <details v-if="section.children.length" open>
        <summary><ChevronDown :size="14" /><button class="outline-link" :class="{ current: active === section.id }" @click.stop.prevent="emit('select', section.id)">{{ section.title }}</button></summary>
        <LessonOutline :sections="section.children" :active="active" @select="emit('select', $event)" />
      </details>
      <button v-else class="outline-link" :class="{ current: active === section.id }" @click="emit('select', section.id)"><FileText :size="14" /><span>{{ section.title }}</span></button>
    </li>
  </ul>
</template>
