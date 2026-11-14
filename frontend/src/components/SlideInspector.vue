<script setup>
import { AlignCenter, AlignLeft, AlignRight, Bold, Italic, Underline, Lock, LockOpen, Trash2 } from 'lucide-vue-next'
import { chartTypes, fonts, labels, shapes, slideFontNames } from '../presentation'

const props = defineProps({ item: Object, slide: { type: Object, required: true }, selected: { type: Array, required: true } })
const emit = defineEmits(['change', 'select', 'edit', 'delete', 'layer', 'group', 'ungroup', 'align', 'background'])
const numberFields = [
  ['x', 'X', -960, 1920], ['y', 'Y', -540, 1080], ['width', '宽度', 8, 1920], ['height', '高度', 8, 1080],
]
function updateNumber(key, lower, upper, event) {
  const number = event.target.valueAsNumber
  if (!Number.isFinite(number)) { event.target.value = Math.round(props.item[key]); return }
  emit('change', { [key]: Math.max(lower, Math.min(upper, number)) })
}
</script>

<template>
  <aside class="presentation-inspector">
    <div class="presentation-inspector-body">
      <template v-if="selected.length > 1">
        <h3>{{ selected.length }} 个对象</h3>
        <div class="presentation-control-row">
          <button class="button secondary" @click="emit('align','left')">左对齐</button>
          <button class="button secondary" @click="emit('align','top')">顶端对齐</button>
          <button class="button secondary" @click="emit('align','center')">水平居中</button>
          <button class="button secondary" @click="emit('align','middle')">垂直居中</button>
          <button class="button secondary" :disabled="selected.length < 3" @click="emit('align','distribute')">横向分布</button>
          <button class="button secondary" @click="emit('group')">组合</button>
          <button class="button secondary" @click="emit('ungroup')">取消组合</button>
          <button class="button secondary" @click="emit('delete')">删除</button>
        </div>
      </template>
      <template v-else-if="item">
        <div class="section-heading"><h3>{{ labels[item.kind] }}</h3>
          <button type="button" class="button subtle icon-only" :aria-label="item.locked ? '解锁对象' : '锁定对象'" @click="emit('change',{ locked:!item.locked })">
            <Lock v-if="item.locked" :size="16" /><LockOpen v-else :size="16" />
          </button>
        </div>
        <fieldset class="presentation-property-group" :disabled="item.locked">
          <div class="presentation-form-cols">
            <label v-for="[key, name, min, max] in numberFields" :key="key">{{ name }}
              <input type="number" :value="Math.round(item[key])" :min="min" :max="max" @change="updateNumber(key,min,max,$event)">
            </label>
          </div>
          <label v-if="!['chart','table'].includes(item.kind)">旋转角度<input type="number" min="-360" max="360" :value="Math.round(item.rotation)" @change="updateNumber('rotation',-360,360,$event)"></label>
          <template v-if="item.kind === 'text'">
            <label>模板用途<select :value="item.role || ''" @change="emit('change',{role:$event.target.value || null})">
              <option value="">固定文字</option><option value="title">页面标题</option><option value="body">教学正文</option>
            </select></label>
            <div class="presentation-form-cols">
              <label>字体<select :value="item.font" @change="emit('change',{font:$event.target.value})"><option v-for="font in fonts" :key="font" :value="font">{{ slideFontNames[font] || font }}</option></select></label>
              <label>字号<input type="number" min="8" max="144" :value="item.size" @change="updateNumber('size',8,144,$event)"></label>
            </div>
            <label class="presentation-color">文字颜色<input type="color" :value="item.color" @change="emit('change',{color:$event.target.value})"></label>
            <div class="presentation-control-row">
              <button v-for="[key, caption, icon] in [['bold','粗体',Bold],['italic','斜体',Italic],['underline','下划线',Underline]]" :key="key"
                class="button subtle icon-only" :aria-label="caption" :aria-pressed="!!item[key]" @click="emit('change',{[key]:!item[key]})"><component :is="icon" :size="16" /></button>
              <button v-for="[key, caption, icon] in [['left','左对齐',AlignLeft],['center','居中',AlignCenter],['right','右对齐',AlignRight]]" :key="key"
                class="button subtle icon-only" :aria-label="caption" :aria-pressed="item.align === key" @click="emit('change',{align:key})"><component :is="icon" :size="16" /></button>
            </div>
          </template>
          <template v-if="item.kind === 'shape'">
            <label>形状<select :value="item.shape" @change="emit('change',{shape:$event.target.value})"><option v-for="(label,key) in shapes" :key="key" :value="key">{{ label }}</option></select></label>
            <label class="presentation-color">填充<input type="color" :value="item.fill" @change="emit('change',{fill:$event.target.value})"></label>
            <label class="presentation-color">边线<input type="color" :value="item.stroke || '#ffffff'" @change="emit('change',{stroke:$event.target.value})"></label>
            <button v-if="item.stroke" class="button subtle" @click="emit('change',{stroke:null})">移除边线</button>
          </template>
          <template v-if="item.kind === 'chart'">
            <label>图表类型<select :value="item.chart" @change="emit('change',{chart:$event.target.value})"><option v-for="(label,key) in chartTypes" :key="key" :value="key">{{ label }}</option></select></label>
            <label v-if="item.chart !== 'pie'" class="presentation-color">图表颜色<input type="color" :value="item.fill" @change="emit('change',{fill:$event.target.value})"></label>
            <label class="presentation-color">标签颜色<input type="color" :value="item.color" @change="emit('change',{color:$event.target.value})"></label>
          </template>
          <button v-if="['text','table','chart','image'].includes(item.kind)" class="button secondary" @click="emit('edit',item.id)">{{ item.kind === 'image' ? '替换图片' : '编辑内容' }}</button>
          <div class="presentation-control-row">
            <button class="button subtle" @click="emit('layer','front')">置顶</button><button class="button subtle" @click="emit('layer','back')">置底</button>
            <button class="button subtle" @click="emit('layer','up')">上移一层</button><button class="button subtle" @click="emit('layer','down')">下移一层</button>
            <button class="button subtle icon-only danger-text" aria-label="删除对象" @click="emit('delete')"><Trash2 :size="16" /></button>
          </div>
        </fieldset>
      </template>
      <template v-else>
        <h3>页面属性</h3>
        <label class="presentation-color">背景颜色<input type="color" :value="slide.background" @change="emit('background',$event.target.value)"></label>
      </template>
      <h3 class="presentation-layer-title">图层</h3>
      <ul class="presentation-layers">
        <li v-for="layer in [...slide.elements].reverse()" :key="layer.id">
          <button :aria-pressed="selected.includes(layer.id)" @click="emit('select',layer.id,$event.shiftKey || $event.ctrlKey || $event.metaKey)">
            <Lock v-if="layer.locked" :size="13" /><span>{{ layer.text?.trim() || labels[layer.kind] }}</span>
          </button>
        </li>
      </ul>
    </div>
  </aside>
</template>
