<script setup>
import { computed, shallowRef, watch } from 'vue'
import { Circle as VCircle, Ellipse as VEllipse, Group as VGroup, Image as VImage, Line as VLine,
  Rect as VRect, Shape as VShape, Text as VText, Wedge as VWedge } from 'vue-konva'
import { labels } from '../presentation'

const props = defineProps({ item: { type: Object, required: true }, editable: Boolean })
const emit = defineEmits(['pick', 'edit', 'moveStart', 'move', 'moveEnd'])
const picture = shallowRef(null)
const palette = ['#216f91', '#6f8db6', '#f3aa5e', '#59a892', '#956bc0', '#db7b76']
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
  const { text, size, font, color, bold, italic, underline, align, width, height } = props.item
  return { text, fontSize: size, fontFamily: font, fill: color, align, width, height, lineHeight: 1.18,
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
const graph = computed(() => {
  const { labels: names, values, width, height } = props.item
  if (!values?.length) return []
  const max = Math.max(...values, 1), total = values.reduce((sum, value) => sum + value, 0)
  const w = (width - 55) / values.length, h = Math.max(1, height - 50)
  let angle = -90
  return values.map((value, i) => {
    const sweep = total ? value * 360 / total : 0
    const result = { name: names[i], value, x: 45 + i * w, width: w, bar: h * value / max,
      y: h * (1 - value / max) + 12, angle, sweep, fill: palette[i % palette.length] }
    angle += sweep
    return result
  })
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
    <VRect :config="{ width: item.width, height: item.height, fill: 'rgba(0,0,0,0.001)' }" />
    <VText v-if="item.kind === 'text'" :config="textConfig" />
    <VImage v-else-if="item.kind === 'image' && picture" :config="{ image: picture, width: item.width, height: item.height }" />
    <template v-else-if="item.kind === 'shape'">
      <VEllipse v-if="item.shape === 'ellipse'" :config="{ x: item.width/2, y: item.height/2, radiusX: item.width/2, radiusY: item.height/2, fill: item.fill, stroke: item.stroke, strokeWidth: 2 }" />
      <VLine v-else-if="item.shape === 'triangle'" :config="{ points: [item.width/2,0,item.width,item.height,0,item.height], closed:true, fill:item.fill, stroke:item.stroke }" />
      <VShape v-else-if="item.shape === 'arrow'" :config="{ fill:item.fill, stroke:item.stroke, sceneFunc: (ctx, node) => {
        const w=item.width,h=item.height
        ctx.beginPath(); ctx.moveTo(0,h*.25); ctx.lineTo(w*.58,h*.25); ctx.lineTo(w*.58,0); ctx.lineTo(w,h*.5)
        ctx.lineTo(w*.58,h); ctx.lineTo(w*.58,h*.75); ctx.lineTo(0,h*.75); ctx.closePath(); ctx.fillStrokeShape(node)
      }, listening: false }" />
      <VRect v-else :config="{ width:item.width, height:item.shape === 'line' ? Math.min(3,item.height) : item.height, cornerRadius:item.shape === 'round' ? 14 : 0, fill:item.fill, stroke:item.stroke, strokeWidth:2 }" />
    </template>
    <template v-else-if="item.kind === 'table'">
      <template v-for="(cell, i) in cells" :key="i">
        <VRect :config="{ ...cell, fill: cell.header ? '#e4ebf4' : '#f5f7fa', stroke: '#b7c5d6', strokeWidth: 1 }" />
        <VText :config="{ ...cell, fontSize: Math.min(item.size || 18,20), fontFamily: item.font, fill: item.color, fontStyle: cell.header ? 'bold':'normal', padding: 8, wrap:'char' }" />
      </template>
    </template>
    <template v-else-if="item.kind === 'chart'">
      <template v-if="item.chart === 'pie'">
        <VWedge v-for="(arc, i) in graph" :key="i" :config="{ x: item.width*.36, y:item.height*.5, angle:arc.sweep, rotation:arc.angle, radius:Math.min(item.width*.33,item.height*.43), fill:arc.fill }" />
        <VText v-for="(arc, i) in graph" :key="i" :config="{ x:item.width*.72, y:18+i*18, width:item.width*.28, text:arc.name, fill:arc.fill, fontSize:13 }" />
      </template>
      <template v-else>
        <VLine :config="{ points:[42,10,42,item.height-36,item.width-8,item.height-36], stroke:'#9baec1', strokeWidth:1 }"/>
        <VLine v-if="item.chart === 'line' && graph.length" :config="{ points:graph.flatMap((bar)=>[bar.x+bar.width/2,bar.y]), stroke:item.fill, strokeWidth:3 }"/>
        <template v-for="(bar, i) in graph" :key="i">
          <VCircle v-if="item.chart === 'line'" :config="{ x:bar.x+bar.width/2, y:bar.y, radius:4, fill:item.fill }" />
          <VRect v-else :config="{ x:bar.x+bar.width*.21,y:bar.y,width:bar.width*.58,height:bar.bar,fill:item.fill }"/>
          <VText :config="{ x:bar.x,y:item.height-31,width:bar.width,text:bar.name,fontSize:13,align:'center',fill:item.color }"/>
          <VText :config="{ x:bar.x,y:bar.y-19,width:bar.width,text:String(bar.value),fontSize:12,align:'center',fill:item.color }"/>
        </template>
      </template>
    </template>
  </VGroup>
</template>
