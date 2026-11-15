<script setup>
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-vue-next'
import { animationEffects, labels } from '../presentation'

const props = defineProps({ slide: { type: Object, required: true }, item: Object })
const emit = defineEmits(['add', 'update', 'remove', 'move', 'select'])

function title(id) {
  const item = props.slide.elements.find((object) => object.id === id)
  return item?.text?.trim().split('\n')[0]?.slice(0, 34) || labels[item?.kind] || '对象'
}

function duration(entry, event) {
  const value = Math.round(event.target.valueAsNumber * 1000)
  if (value < 100 || value > 5000 || !Number.isFinite(value)) {
    event.target.value = entry.duration_ms / 1000
    return
  }
  emit('update', entry.id, { duration_ms: value })
}
</script>

<template>
  <section class="presentation-animation-list" aria-label="当前页动画">
    <div class="section-heading">
      <h3>对象动画</h3>
      <button type="button" class="button subtle icon-only" :disabled="!item || (slide.animations?.length || 0) >= 50"
        title="为选中对象添加动画" aria-label="添加动画" @click="emit('add')"><Plus :size="17" /></button>
    </div>
    <p v-if="!slide.animations?.length && !item" class="muted">选中对象后添加动画</p>
    <article v-for="(entry,index) in slide.animations" :key="entry.id" class="presentation-animation-row" :aria-label="'动画 ' + (index + 1)">
      <div class="presentation-animation-heading">
        <button type="button" class="button subtle" :title="title(entry.target_id)" @click="emit('select',entry.target_id)">
          {{ index + 1 }} · {{ title(entry.target_id) }}
        </button>
        <button type="button" class="button subtle icon-only" aria-label="提前播放" :disabled="index === 0" @click="emit('move',index,-1)"><ArrowUp :size="13" /></button>
        <button type="button" class="button subtle icon-only" aria-label="延后播放" :disabled="index === slide.animations.length-1" @click="emit('move',index,1)"><ArrowDown :size="13" /></button>
        <button type="button" class="button subtle icon-only danger-text" aria-label="移除动画" @click="emit('remove',entry.id)"><Trash2 :size="13" /></button>
      </div>
      <div class="presentation-form-cols">
        <label>效果<select aria-label="动画效果" :value="entry.effect" @change="emit('update',entry.id,{effect:$event.target.value})">
          <option v-for="(name,key) in animationEffects" :key="key" :value="key">{{ name }}</option>
        </select></label>
        <label>触发<select aria-label="动画触发" :value="entry.trigger" @change="emit('update',entry.id,{trigger:$event.target.value})">
          <option value="click">点击时</option><option value="after">自动接续</option>
        </select></label>
      </div>
      <label>时长（秒）<input aria-label="动画时长（秒）" type="number" min=".1" max="5" step=".1" :value="entry.duration_ms / 1000"
        @change="duration(entry,$event)"></label>
    </article>
  </section>
</template>
