<script setup>
import { computed } from 'vue'
import { renderFormula } from '../examMath'

const props = defineProps({ item: { type: Object, required: true }, scale: { type: Number, required: true }, motion: Object })
const formula = computed(() => {
  try { return renderFormula(props.item.latex, true) }
  catch { return '' }
})
const styles = computed(() => {
  const { x, y, width, height, rotation, size, align, color } = props.item
  const { opacity = 1, dy = 0, scale = 1 } = props.motion || {}
  return { left: x + width * (1 - scale) / 2 + 'px', top: y + dy + height * (1 - scale) / 2 + 'px',
    width: width + 'px', height: height + 'px', opacity, transform: `rotate(${rotation}deg) scale(${scale})`,
    fontSize: size / 1.21 + 'px', textAlign: align, color }
})
</script>

<template>
  <div class="presentation-formula-overlay" :style="{transform:'scale(' + scale + ')'}">
    <div class="presentation-formula" :style="styles">
      <span v-if="formula" v-html="formula" />
      <span v-else>{{ item.latex }}</span>
    </div>
  </div>
</template>
