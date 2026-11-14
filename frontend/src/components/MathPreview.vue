<script setup>
import { computed } from 'vue'
import { mathSegments, renderFormula } from '../examMath'

const props = defineProps({ source: { type: String, default: '' } })
const segments = computed(() => mathSegments(props.source).map((segment) => {
  if (!segment.math) return segment
  try { return { ...segment, html: renderFormula(segment.text, segment.display) } }
  catch { return { ...segment, invalid: true } }
}))
</script>

<template>
  <span class="math-preview">
    <template v-for="(segment, index) in segments" :key="index">
      <span v-if="segment.html" v-html="segment.html" />
      <span v-else-if="segment.invalid" class="math-invalid" title="公式语法有误">{{ segment.original }}</span>
      <template v-else>{{ segment.text }}</template>
    </template>
  </span>
</template>
