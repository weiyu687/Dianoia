<script setup>
import { computed } from 'vue'
import { renderFormula } from '../examMath'

const props = defineProps({ item: { type: Object, required: true }, scale: { type: Number, required: true } })
const formula = computed(() => {
  try { return renderFormula(props.item.latex, true) }
  catch { return '' }
})
const styles = computed(() => {
  const { x, y, width, height, rotation, size, align, color } = props.item
  return { left: x + 'px', top: y + 'px', width: width + 'px', height: height + 'px',
    transform: 'rotate(' + rotation + 'deg)', fontSize: size / 1.21 + 'px', textAlign: align, color }
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
