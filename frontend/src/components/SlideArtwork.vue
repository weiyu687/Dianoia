<script setup>
import { computed, shallowRef, watch } from 'vue'
import { Arrow as VArrow, Ellipse as VEllipse, Group as VGroup, Image as VImage, Line as VLine,
  Rect as VRect, Text as VText } from 'vue-konva'
import { labels } from '../presentation'
import SlideChart from './SlideChart.vue'

const props = defineProps({ item: { type: Object, required: true }, editable: Boolean })
const emit = defineEmits(['pick', 'edit', 'moveStart', 'move', 'moveEnd'])
const picture = shallowRef(null)
const polygons = {
  triangle:[.5,0,1,1,0,1], diamond:[.5,0,1,.5,.5,1,0,.5], hexagon:[.24,0,.76,0,1,.5,.76,1,.24,1,0,.5],
  parallelogram:[.2,0,1,0,.8,1,0,1], trapezoid:[.22,0,.78,0,1,1,0,1],
  chevron:[0,0,.72,0,1,.5,.72,1,0,1,.3,.5], pentagon:[.5,0,1,.38,.81,1,.19,1,0,.38],
  arrow:[0,.25,.58,.25,.58,0,1,.5,.58,1,.58,.75,0,.75],
  arrowLeft:[1,.25,.42,.25,.42,0,0,.5,.42,1,.42,.75,1,.75],
  arrowUp:[.25,1,.25,.42,0,.42,.5,0,1,.42,.75,.42,.75,1],
  arrowDown:[.25,0,.25,.58,0,.58,.5,1,1,.58,.75,.58,.75,0],
  star:[.5,0,.62,.35,1,.38,.71,.61,.8,1,.5,.77,.2,1,.29,.61,0,.38,.38,.35],
  callout:[0,0,1,0,1,.76,.43,.76,.22,1,.22,.76,0,.76],
}
const polygon = computed(() => polygons[props.item.shape]?.map((value, i) => value * (i % 2 ? props.item.height : props.item.width)))
const line = computed(() => {
  const { width, height, fill, stroke, line_style, line_width } = props.item
  return { points:[0,0,width,height], fill:stroke || fill, stroke:stroke || fill, strokeWidth:line_width || 2,
    dash:line_style === 'dash' ? [8,6] : line_style === 'dot' ? [2,5] : [], pointerWidth:10, pointerLength:12,
    hitStrokeWidth:14, lineCap:'round' }
})
watch(() => props.item.image, (source, _, dispose) => {
  picture.value = null
  if (!source) return
  const image = new Image()
  image.onload = () => { picture.value = image }
  image.src = source
  dispose(() => { image.onload = null })
}, { immediate: true })

const config = computed(() => {
  const { id, x, y, rotation, width, height, locked } = props.item
  return { id, name: labels[props.item.kind], x, y, rotation, width, height,
    draggable: props.editable && !locked, listening: props.editable,
    onMousedown: pick, onTap: pick, onDblclick: edit, onDbltap: edit,
    onDragstart: dragStart, onDragmove: dragMove, onDragend: dragEnd }
})
const textConfig = computed(() => {
  const { text, size, font, color, bold, italic, underline, align, width, height, line_height, spacing } = props.item
  return { text, fontSize: size, fontFamily: font, fill: color, align, width, height, lineHeight: line_height || 1.18, letterSpacing: spacing || 0,
    fontStyle: [italic && 'italic', bold && 'bold'].filter(Boolean).join(' ') || 'normal',
    textDecoration: underline ? 'underline' : '', wrap: 'char' }
})
const cells = computed(() => {
  const { rows, width, height } = props.item
  if (!rows?.length || !rows[0].length) return []
  const w = width / rows[0].length, h = height / rows.length
  return rows.flatMap((row, r) => row.map((text, c) => ({
    x: c * w, y: r * h, width: w, height: h, text, header: r === 0,
  })))
})
function pick(event) {
  if (!props.editable) return
  event.cancelBubble = true
  emit('pick', props.item.id, event.evt)
}

function edit(event) {
  if (!props.editable || props.item.locked) return
  event.cancelBubble = true
  emit('edit', props.item.id)
}
function dragStart(event) { emit('moveStart', props.item.id, event) }
function dragMove(event) { emit('move', props.item.id, event) }
function dragEnd(event) { emit('moveEnd', props.item.id, event) }
</script>

<template>
  <VGroup :config="config">
    <VRect v-if="!['connector','connectorArrow'].includes(item.shape) || item.kind !== 'shape'" :config="{ width: item.width, height: item.height, fill: 'rgba(0,0,0,0.001)' }" />
    <VText v-if="item.kind === 'text'" :config="textConfig" />
    <VImage v-else-if="item.kind === 'image' && picture" :config="{ image: picture, width: item.width, height: item.height }" />
    <template v-else-if="item.kind === 'shape'">
      <VEllipse v-if="item.shape === 'ellipse'" :config="{ x: item.width/2, y: item.height/2, radiusX: item.width/2, radiusY: item.height/2, fill: item.fill, stroke: item.stroke, strokeWidth: 2 }" />
      <VLine v-else-if="item.shape === 'connector'" :config="line" />
      <VArrow v-else-if="item.shape === 'connectorArrow'" :config="line" />
      <VLine v-else-if="polygon" :config="{ points:polygon,closed:true,fill:item.fill,stroke:item.stroke,strokeWidth:2 }" />
      <VRect v-else :config="{ width:item.width, height:item.shape === 'line' ? Math.min(3,item.height) : item.height, cornerRadius:item.shape === 'round' ? 14 : 0, fill:item.fill, stroke:item.stroke, strokeWidth:2 }" />
    </template>
    <template v-else-if="item.kind === 'table'">
      <template v-for="(cell, i) in cells" :key="i">
        <VRect :config="{ ...cell, fill: cell.header ? item.header_fill || '#e4ebf4' : item.header_color ? item.fill : '#f5f7fa', stroke: '#b7c5d6', strokeWidth: 1 }" />
        <VText :config="{ ...cell, fontSize: Math.min(item.size || 18,20), fontFamily: item.font, fill: cell.header ? item.header_color || item.color : item.color, fontStyle: cell.header ? 'bold':'normal', padding: 6, wrap:'char' }" />
      </template>
    </template>
    <SlideChart v-else-if="item.kind === 'chart'" :item="item" />
  </VGroup>
</template>
