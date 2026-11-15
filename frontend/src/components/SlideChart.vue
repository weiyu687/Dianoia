<script setup>
import { computed } from 'vue'
import { Arc as VArc, Circle as VCircle, Group as VGroup, Line as VLine, Rect as VRect, Text as VText } from 'vue-konva'

const { item } = defineProps({ item: { type: Object, required: true } })
const palette = ['#4382ac', '#7285ce', '#edab60', '#5bb49c', '#b083bd', '#e18380']
const graph = computed(() => {
  const { chart, width, height, values, labels, chart_title: title } = item
  const top = title ? 40 : 14
  const bottom = Math.max(top + 1, height - 31)
  const left = chart === 'bar' ? Math.min(width * .34, 124) : Math.min(width * .16, 48)
  const right = Math.max(left + 1, width - 16)
  const min = Math.min(...values, 0), max = Math.max(...values, 0)
  const span = max - min || 1
  const y = (n) => bottom - (n - min) / span * (bottom - top)
  const x = (n) => left + (n - min) / span * (right - left)
  const ys = y(0), xs = x(0)
  const dx = (right - left) / labels.length, dy = (bottom - top) / labels.length
  const numbers = labels.map(Number)
  const firstX = Math.min(...numbers), rangeX = Math.max(...numbers) - firstX || 1
  const center = [width * (['pie','donut'].includes(chart) ? .34 : .5), (top + bottom) / 2]
  const radius = Math.max(1, Math.min(width * .24, (bottom - top) * .45))
  const radial = (i, fraction) => {
    const angle = i * 2 * Math.PI / labels.length - Math.PI / 2
    return [center[0] + radius * fraction * Math.cos(angle), center[1] + radius * fraction * Math.sin(angle)]
  }
  const total = values.reduce((sum, value) => sum + value, 0)
  let rotation = -90
  const marks = labels.map((label, i) => {
    const value = values[i]
    const angle = total > 0 ? Math.max(0, value) * 360 / total : 0
    const point = {
      label, value, angle, rotation, fill: palette[i % palette.length],
      x: chart === 'scatter' ? left + (numbers[i] - firstX) / rangeX * (right - left) : left + (i + .5) * dx,
      y: y(value), barX: x(value), barY: top + (i + .5) * dy,
      p: radial(i, value / (max || 1)), edge: radial(i, 1), caption: radial(i, 1.18),
    }
    rotation += angle
    return point
  })
  return { top, bottom, left, right, ys, xs, dx, dy, marks, center, radius }
})
</script>

<template>
  <VGroup :config="{ listening:false, clipWidth:item.width, clipHeight:item.height }">
    <VText v-if="item.chart_title" :config="{ x:6,y:7,width:item.width-12,text:item.chart_title,fontSize:16,fontStyle:'bold',align:'center',fill:item.color }" />
    <template v-if="['pie','donut'].includes(item.chart)">
      <template v-for="(point,i) in graph.marks" :key="i">
        <VArc :config="{ x:graph.center[0],y:graph.center[1],angle:point.angle,rotation:point.rotation,
          innerRadius:item.chart === 'donut' ? graph.radius*.53 : 0,outerRadius:graph.radius,fill:point.fill }" />
        <VRect :config="{ x:item.width*.65,y:graph.top+i*17,width:10,height:10,fill:point.fill }" />
        <VText :config="{ x:item.width*.65+15,y:graph.top+i*17,width:item.width*.34-15,text:point.label+'  '+point.value,fontSize:12,fill:item.color }" />
      </template>
    </template>
    <template v-else-if="item.chart === 'radar'">
      <VLine v-for="ratio in [.33,.66,1]" :key="ratio" :config="{ closed:true, stroke:'#91a0ad', strokeWidth:1,
        points:graph.marks.flatMap(({edge})=>edge.map((coordinate,i)=>graph.center[i]+(coordinate-graph.center[i])*ratio)) }" />
      <VLine :config="{ closed:true, points:graph.marks.flatMap((point)=>point.p),stroke:item.fill,fill:item.fill,opacity:.62,strokeWidth:2 }" />
      <VText v-for="(point,i) in graph.marks" :key="i" :config="{ x:point.caption[0]-53,y:point.caption[1]-7,width:106,
        text:point.label,align:'center',fontSize:12,fill:item.color }" />
    </template>
    <template v-else-if="item.chart === 'bar'">
      <VLine :config="{ points:[graph.xs,graph.top,graph.xs,graph.bottom],stroke:'#91a0ad',strokeWidth:1 }" />
      <template v-for="(point,i) in graph.marks" :key="i">
        <VRect :config="{ x:Math.min(graph.xs,point.barX),y:point.barY-graph.dy*.28,width:Math.abs(point.barX-graph.xs),height:graph.dy*.56,fill:item.fill }" />
        <VText :config="{ x:2,y:point.barY-6,width:graph.left-6,text:point.label,align:'right',fontSize:12,fill:item.color }" />
        <VText :config="{ x:Math.max(graph.left,Math.min(item.width-52,point.barX + (point.value < 0 ? -40 : 4))),y:point.barY-6,
          width:48,text:String(point.value),align:point.value < 0 ? 'right' : 'left',fontSize:12,fill:item.color }" />
      </template>
    </template>
    <template v-else>
      <VLine :config="{ points:[graph.left,graph.top,graph.left,graph.bottom,graph.right,graph.bottom],stroke:'#91a0ad',strokeWidth:1 }" />
      <VLine v-if="graph.ys !== graph.bottom" :config="{ points:[graph.left,graph.ys,graph.right,graph.ys],stroke:'#91a0ad',strokeWidth:1,dash:[4,4] }" />
      <VLine v-if="item.chart === 'area'" :config="{ closed:true,
        points:[graph.marks[0].x,graph.ys,...graph.marks.flatMap(({x,y})=>[x,y]),graph.marks.at(-1).x,graph.ys],fill:item.fill,opacity:.45 }" />
      <VLine v-if="['line','area'].includes(item.chart)" :config="{ points:graph.marks.flatMap(({x,y})=>[x,y]),stroke:item.fill,strokeWidth:2 }" />
      <template v-for="(point,i) in graph.marks" :key="i">
        <VRect v-if="item.chart === 'column'" :config="{ x:point.x-graph.dx*.27,y:Math.min(point.y,graph.ys),width:graph.dx*.54,height:Math.abs(point.y-graph.ys),fill:item.fill }" />
        <VCircle v-else :config="{ x:point.x,y:point.y,radius:4,fill:item.fill }" />
        <VText :config="{ x:point.x-graph.dx/2,y:graph.bottom+7,width:graph.dx,text:point.label,fontSize:12,align:'center',fill:item.color }" />
        <VText :config="{ x:point.x-38,y:Math.max(graph.top-13,point.y-17),width:76,text:String(point.value),fontSize:12,align:'center',fill:item.color }" />
      </template>
    </template>
  </VGroup>
</template>
