<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ item: { type: Object, required: true }, endpoint: { type: String, required: true },
  scale: { type: Number, required: true } })
const error = ref(false)
const src = computed(() => '/api' + props.endpoint + '/media/' + encodeURIComponent(props.item.media_id))
const style = computed(() => {
  const { x, y, width, height, rotation } = props.item
  return { left: x + 'px', top: y + 'px', width: width + 'px', height: height + 'px', '--slide-object-rotation': rotation + 'deg' }
})
</script>

<template>
  <div class="presentation-media-overlay" :style="{transform:'scale(' + scale + ')'}">
    <div class="presentation-media-player presentation-object-motion" :style="style" data-presentation-media @click.stop>
      <p v-if="error" class="presentation-media-error" role="status">无法播放 {{ item.text }}</p>
      <video v-else-if="item.kind === 'video'" :src="src" :aria-label="item.text" controls playsinline preload="metadata" @error="error = true" />
      <audio v-else :src="src" :aria-label="item.text" controls preload="metadata" @error="error = true" />
    </div>
  </div>
</template>
