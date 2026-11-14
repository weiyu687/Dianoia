<script setup>
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import { Layer as VLayer, Rect as VRect, Stage as VStage } from 'vue-konva'
import SlideArtwork from './SlideArtwork.vue'
import { height, width } from '../presentation'

const props = defineProps({ slide: { type: Object, required: true } })
const SlideFormula = defineAsyncComponent(() => import('./SlideFormula.vue'))
const equations = computed(() => props.slide.elements.filter((item) => item.kind === 'formula'))
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
    <SlideFormula v-for="item in equations" :key="item.id" :item="item" :scale="ratio" />
  </div>
</template>
