<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({ item: { type: Object, required: true }, endpoint: { type: String, required: true },
  motion: Object, scale: { type: Number, required: true } })
const error = ref(false)
const player = ref(null)
const src = computed(() => '/api' + props.endpoint + '/media/' + encodeURIComponent(props.item.media_id))
const visible = computed(() => props.motion?.opacity !== 0)
const style = computed(() => {
  const { x, y, width, height, rotation } = props.item
  const { opacity = 1, dy = 0, scale = 1 } = props.motion || {}
  return { left: x + width * (1 - scale) / 2 + 'px', top: y + dy + height * (1 - scale) / 2 + 'px',
    width: width + 'px', height: height + 'px', opacity,
    transform: `rotate(${rotation}deg) scale(${scale})` }
})
watch(visible, (isVisible) => { if (!isVisible) player.value?.pause() })
</script>

<template>
  <div class="presentation-media-overlay" :style="{transform:'scale(' + scale + ')'}">
    <div v-show="visible" class="presentation-media-player" :style="style" data-presentation-media @click.stop>
      <p v-if="error" class="presentation-media-error" role="status">无法播放 {{ item.text }}</p>
      <video v-else-if="item.kind === 'video'" ref="player" :src="src" :aria-label="item.text" controls playsinline preload="metadata" @error="error = true" />
      <audio v-else ref="player" :src="src" :aria-label="item.text" controls preload="metadata" @error="error = true" />
    </div>
  </div>
</template>
