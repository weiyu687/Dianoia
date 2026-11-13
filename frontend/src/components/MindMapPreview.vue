<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { createCanvas } from '../mindMapCanvas'

const props = defineProps({ document: { type: Object, required: true } })
const host = ref(null)
let observer
let resize
let canvas

onMounted(() => {
  observer = new IntersectionObserver(([entry]) => {
    if (!entry.isIntersecting) return
    observer.disconnect()
    canvas = createCanvas(host.value, props.document, { readonly: true, full: true })
    resize = new ResizeObserver(() => {
      if (host.value?.clientWidth) {
        canvas.resize()
        canvas.view.fit()
      }
    })
    resize.observe(host.value)
  })
  observer.observe(host.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  resize?.disconnect()
  canvas?.destroy()
})
</script>

<template>
  <div ref="host" class="map-preview" aria-hidden="true" />
</template>
