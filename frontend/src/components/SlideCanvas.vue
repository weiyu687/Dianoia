<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Layer as VLayer, Line as VLine, Rect as VRect, Stage as VStage, Transformer as VTransformer } from 'vue-konva'
import SlideArtwork from './SlideArtwork.vue'
import { height, width } from '../presentation'

const props = defineProps({ slide: { type: Object, required: true }, selected: { type: Array, default: () => [] },
  zoom: { type: Number, default: 1 }, editable: Boolean })
const emit = defineEmits(['select', 'edit', 'move', 'transform'])
const SlideFormula = defineAsyncComponent(() => import('./SlideFormula.vue'))
const viewport = ref(null)
const layer = ref(null)
const transformer = ref(null)
const viewWidth = ref(700)
const viewHeight = ref(440)
const scale = computed(() => Math.max(.15, Math.min(1.4, viewWidth.value / width, viewHeight.value / height) * props.zoom))
const moving = ref({})
const guides = ref({ x: null, y: null })
const equations = computed(() => props.slide.elements.filter((item) => item.kind === 'formula')
  .map((item) => ({ ...item, ...moving.value[item.id] })))
let observer, drag
onMounted(() => {
  observer = new ResizeObserver(([entry]) => {
    viewWidth.value = entry.contentRect.width - 6
    viewHeight.value = entry.contentRect.height - 6
  })
  observer.observe(viewport.value)
})
onUnmounted(() => observer?.disconnect())
watch(() => [props.selected, props.slide, props.editable], async () => {
  await nextTick()
  const handle = transformer.value?.getNode()
  const groupLayer = layer.value?.getNode()
  if (!handle || !groupLayer) return
  const ids = new Set(props.selected)
  const editable = groupLayer.getChildren().filter((node) => ids.has(node.id()) &&
    !props.slide.elements.find((item) => item.id === node.id())?.locked)
  handle.nodes(editable)
  handle.getLayer()?.batchDraw()
}, { deep: true, immediate: true })

function pick(id, event) { emit('select', id, !!(event?.shiftKey || event?.ctrlKey || event?.metaKey)) }
function dragStart(id, event) {
  const node = event.target
  const frame = props.slide.elements.find((item) => item.id === id)
  const selected = props.selected.includes(id) ? new Set(props.selected) : new Set([id])
  drag = { id: node.id(), x: frame.x, y: frame.y, items: props.slide.elements.filter((item) => selected.has(item.id) && !item.locked)
    .map((item) => ({ id: item.id, x: item.x, y: item.y })) }
}
function dragMove(id, event) {
  if (!drag || id !== drag.id) return
  const node = event.target
  if (event.evt?.altKey || node.rotation()) guides.value = { x: null, y: null }
  else {
    const movingIds = new Set(drag.items.map((item) => item.id))
    const still = props.slide.elements.filter((item) => !movingIds.has(item.id) && !item.rotation)
    const anchors = (origin, extent) => [origin, origin + extent / 2, origin + extent]
    const nearest = (axis, dimension, boardExtent) => {
      const targets = anchors(0, boardExtent).concat(still.flatMap((item) => anchors(item[axis], item[dimension])))
      let delta = 6 / scale.value, guide = null
      for (const current of anchors(node[axis](), node[dimension]())) {
        for (const target of targets) {
          if (Math.abs(target - current) < Math.abs(delta)) { delta = target - current; guide = target }
        }
      }
      return { point: node[axis]() + (guide === null ? 0 : delta), guide }
    }
    const horizontal = nearest('x', 'width', width), vertical = nearest('y', 'height', height)
    node.position({ x: horizontal.point, y: vertical.point })
    guides.value = { x: horizontal.guide, y: vertical.guide }
  }
  const dx = node.x() - drag.x, dy = node.y() - drag.y
  moving.value = Object.fromEntries(drag.items.map((item) => [item.id, { x: item.x + dx, y: item.y + dy }]))
  const groupLayer = layer.value.getNode()
  for (const item of drag.items) {
    const other = groupLayer.getChildren().find((candidate) => candidate.id() === item.id)
    if (other && other !== node) other.position({ x: item.x + dx, y: item.y + dy })
  }
}
function dragEnd(id, event) {
  if (!drag || id !== drag.id) return
  const { x, y } = event.target.position()
  emit('move', drag.items.map((item) => ({ id: item.id, x: item.x + x - drag.x, y: item.y + y - drag.y })))
  drag = null
  moving.value = {}
  guides.value = { x: null, y: null }
}
function transform() {
  const nodes = transformer.value.getNode().nodes()
  emit('transform', nodes.map((node) => {
    const next = { id: node.id(), x: node.x(), y: node.y(), rotation: node.rotation(),
      width: Math.min(1920, Math.max(8, node.width() * node.scaleX())),
      height: Math.min(1080, Math.max(8, node.height() * node.scaleY())) }
    node.scale({ x: 1, y: 1 })
    return next
  }))
}
function empty(event) { if (!event.target.id()) emit('select', '', false) }
</script>

<template>
  <div ref="viewport" class="presentation-canvas" :class="{ 'presentation-playing': !editable }">
    <div class="presentation-board" :style="{ width: (scale * width) + 'px', height: (scale * height) + 'px' }">
      <VStage :config="{ width: scale * width, height: scale * height, onMousedown: empty, onTap: empty }">
        <VLayer ref="layer" :config="{ scaleX: scale, scaleY: scale }">
          <VRect :config="{ width, height, fill: slide.background }" />
          <SlideArtwork v-for="item in slide.elements" :key="item.id" :item="item" :editable="editable"
            @pick="pick" @edit="emit('edit', $event)" @move-start="dragStart" @move="dragMove" @move-end="dragEnd" />
          <VLine v-if="guides.x !== null" :config="{ points:[guides.x,0,guides.x,height], stroke:'#7974ff', strokeWidth:1, dash:[5,4], listening:false }" />
          <VLine v-if="guides.y !== null" :config="{ points:[0,guides.y,width,guides.y], stroke:'#7974ff', strokeWidth:1, dash:[5,4], listening:false }" />
          <VTransformer v-if="editable" ref="transformer" :config="{ flipEnabled:false, rotateEnabled:selected.length === 1 &&
            !slide.elements.some((item) => selected.includes(item.id) && ['table','chart'].includes(item.kind)),
            borderStroke:'#6578ed', anchorStroke:'#6578ed', anchorSize:8, anchorCornerRadius:2,
            boundBoxFunc: (previous, next) => next.width < 8 || next.height < 8 ? previous : next,
            onTransformend: transform }" />
        </VLayer>
      </VStage>
      <SlideFormula v-for="item in equations" :key="item.id" :item="item" :scale="scale" />
    </div>
  </div>
</template>
