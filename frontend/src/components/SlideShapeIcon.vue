<script setup>
import { computed } from 'vue'
import { shapePolygons } from '../presentation'

const props = defineProps({ shape: { type: String, required: true } })
const polygon = computed(() => {
  const points = shapePolygons[props.shape]
  return points?.reduce((pairs, value, index) => {
    if (index % 2 === 0) pairs.push([3 + 18 * value, 4 + 16 * points[index + 1]].join(','))
    return pairs
  }, []).join(' ')
})
</script>

<template>
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <ellipse v-if="shape === 'ellipse'" cx="12" cy="12" rx="9" ry="7" />
    <polygon v-else-if="polygon" :points="polygon" />
    <path v-else-if="shape === 'connectorArrow'" d="M4 20 20 4m-8 0h8v8" />
    <path v-else-if="shape === 'connector'" d="M4 20 20 4" />
    <rect v-else x="3" y="4" width="18" height="16" :rx="shape === 'round' ? 4 : 0" />
  </svg>
</template>
