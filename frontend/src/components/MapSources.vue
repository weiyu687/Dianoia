<script setup>
import { ref } from 'vue'
import { Plus, X } from 'lucide-vue-next'
import { api } from '../api'

const props = defineProps({ modelValue: { type: Array, required: true }, resources: { type: Array, required: true } })
const emit = defineEmits(['update:modelValue'])
const error = ref('')
const outlines = ref({})
const pending = ref({})

function flatten(nodes, depth = 0) {
  return nodes.flatMap((node) => [{ ...node, depth }, ...flatten(node.children, depth + 1)])
}

function update(index, fields) {
  emit('update:modelValue', props.modelValue.map((source, position) => position === index ? { ...source, ...fields } : source))
}

async function load(id) {
  if (!id || outlines.value[id] || pending.value[id]) return
  pending.value[id] = true
  error.value = ''
  try {
    const file = await api(`/resources/${id}`)
    outlines.value[id] = flatten(file.outline)
  } catch (failure) { error.value = failure.message }
  finally { delete pending.value[id] }
}

function choose(index, id) {
  const max = props.resources.find((resource) => resource.id === id)?.page_count || 1
  update(index, { resource_id: id, start: 1, end: max })
  load(id)
}
</script>

<template>
  <div class="map-source-picker stack">
    <div class="section-heading">
      <strong>选择资料</strong>
      <button class="button secondary" type="button" :disabled="!resources.length || modelValue.length >= 12"
        @click="emit('update:modelValue', [...modelValue, { resource_id: '', start: 1, end: 1 }])"><Plus :size="15" /> 添加资料</button>
    </div>
    <p v-if="!resources.length" class="muted">请先在当前课程的资料库中入库文件。</p>
    <div v-for="(source, index) in modelValue" :key="index" class="source-picker">
      <div class="section-heading">
        <label>资料<select :aria-label="`资料 ${index + 1}`" :value="source.resource_id" required @change="choose(index, $event.target.value)">
          <option value="">选择资料</option>
          <option v-if="source.resource_id && !resources.some((file) => file.id === source.resource_id)" :value="source.resource_id">资料已不可用</option>
          <option v-for="file in resources" :key="file.id" :value="file.id">{{ file.title }}</option>
        </select></label>
        <button type="button" class="button subtle icon-only" aria-label="移除资料" @click="emit('update:modelValue', modelValue.filter((_, position) => position !== index))"><X :size="17" /></button>
      </div>
      <div class="actions map-range">
        <label>开始页<input type="number" min="1" :max="source.end || undefined" required :value="source.start" @input="update(index, { start: $event.target.valueAsNumber })"></label>
        <label>结束页<input type="number" :min="source.start || 1" :max="resources.find((file) => file.id === source.resource_id)?.page_count" required :value="source.end" @input="update(index, { end: $event.target.valueAsNumber })"></label>
        <button v-if="source.resource_id && !outlines[source.resource_id] && resources.some((file) => file.id === source.resource_id)" class="button subtle" type="button" :disabled="pending[source.resource_id]" @click="load(source.resource_id)">加载章节</button>
      </div>
      <label v-if="outlines[source.resource_id]?.length">章节目录<select :aria-label="`章节目录 ${index + 1}`" :key="`${source.resource_id}:${source.start}:${source.end}`" @change="(event) => {
        const chapter = outlines[source.resource_id][event.target.value]
        if (chapter) update(index, { start: chapter.start, end: chapter.end })
      }">
        <option value="">选择章节以填入页码</option>
        <option v-for="(chapter, number) in outlines[source.resource_id]" :key="number" :value="number">{{ '　'.repeat(chapter.depth) }}{{ chapter.title }} · {{ chapter.start }}–{{ chapter.end }} 页</option>
      </select></label>
      <p v-else-if="outlines[source.resource_id]" class="muted">该资料暂无目录，可直接填写页码。</p>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>
