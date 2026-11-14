<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Layer as VLayer, Rect as VRect, Stage as VStage } from 'vue-konva'
import SlideArtwork from './SlideArtwork.vue'
import { height, width } from '../presentation'

const props = defineProps({ slide: { type: Object, required: true } })
const frame = ref(null)
const measure = ref(200)
const ratio = computed(() => measure.value / width)
let observer
onMounted(() => {
  observer = new ResizeObserver(([entry]) => { measure.value = Math.max(1, entry.contentRect.width) })
  observer.observe(frame.value)
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <div ref="frame" class="presentation-thumbnail" aria-hidden="true" :style="{ background: slide.background }">
    <VStage :config="{ width: measure, height: measure * height / width, listening: false }">
      <VLayer :config="{ scaleX: ratio, scaleY: ratio, listening: false }">
        <VRect :config="{ width, height, fill: slide.background }" />
        <SlideArtwork v-for="item in slide.elements" :key="item.id" :item="item" />
      </VLayer>
    </VStage>
  </div>
</template>
