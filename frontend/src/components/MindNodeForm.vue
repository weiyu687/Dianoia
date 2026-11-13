<script setup>
import { computed, ref } from 'vue'
import katex from 'katex'
import 'katex/dist/katex.min.css'

const props = defineProps({
  mode: { type: String, required: true },
  node: { type: Object, required: true },
  targets: { type: Array, default: () => [] },
  linked: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'cancel', 'jump', 'unlink'])
const field = ref({
  labels: (props.node.labels || []).join('\n'), summary: props.node.summary || '',
  frame: props.node.frame?.text || '', icon: props.node.icon || '', url: props.node.hyperlink?.url || '',
  label: props.node.hyperlink?.label || '', formula: props.node.formula || '', code: props.node.code || '',
  rows: (props.node.table?.rows || [['', ''], ['', '']]).map((row) => [...row]), target: '', image: null,
})
const error = ref('')
const reading = ref(false)
const formulaHtml = computed(() => {
  try {
    return field.value.formula.trim() ? katex.renderToString(field.value.formula, { trust: false, maxExpand: 500, maxSize: 12 }) : ''
  } catch { return '' }
})
const iconChoices = {
  priority_1: '优先级 1', priority_2: '优先级 2', priority_3: '优先级 3',
  progress_1: '进度 1', progress_4: '进度 4', sign_1: '标记 1', sign_2: '标记 2', sign_3: '标记 3',
}

async function chooseImage(event) {
  const file = event.target.files[0]
  field.value.image = null
  error.value = ''
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(file.type) || file.size > 10 * 1024 * 1024) {
    error.value = '请选择 10 MB 以内的 PNG、JPEG、WebP 或 GIF'
    return
  }
  reading.value = true
  try {
    const bitmap = await createImageBitmap(file)
    try {
      const canvas = document.createElement('canvas')
      const scale = Math.min(1, 640 / Math.max(bitmap.width, bitmap.height))
      canvas.width = Math.max(1, Math.round(bitmap.width * scale))
      canvas.height = Math.max(1, Math.round(bitmap.height * scale))
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height)
      let data = canvas.toDataURL('image/webp', 0.82)
      if (data.length > 220000) data = canvas.toDataURL('image/webp', 0.55)
      if (data.length > 220000 || !data.startsWith('data:image/webp;base64,')) throw new Error()
      field.value.image = { data_url: data, width: canvas.width, height: canvas.height }
    } finally { bitmap.close() }
  } catch { error.value = '无法处理此图片，请换用较小的图片' }
  finally { reading.value = false }
}

function submit() {
  error.value = ''
  const value = field.value
  switch (props.mode) {
    case 'labels': {
      const labels = [...new Set(value.labels.split('\n').map((text) => text.trim()).filter(Boolean))]
      if (labels.length > 4 || labels.some((label) => label.length > 32)) {
        error.value = '最多 4 条标注，每条最多 32 字'
        return
      }
      emit('save', labels)
      break
    }
    case 'hyperlink': {
      if (!value.url.trim()) { emit('save', null); return }
      try {
        const url = new URL(value.url.trim())
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error()
        emit('save', { url: url.href, label: value.label.trim() })
      } catch { error.value = '请输入以 https:// 或 http:// 开头的网址' }
      break
    }
    case 'formula':
      if (value.formula.trim() && !formulaHtml.value) { error.value = '请检查 LaTeX 语法'; return }
      emit('save', value.formula.trim())
      break
    case 'table':
      emit('save', { rows: value.rows })
      break
    case 'nodeLinks':
      if (value.target) emit('save', value.target)
      break
    default:
      emit('save', value[props.mode])
  }
}

function remove() {
  emit('save', ['image', 'table', 'frame'].includes(props.mode) ? null : '')
}
</script>

<template>
  <form class="stack" @submit.prevent="submit">
    <label v-if="mode === 'labels'">标注文字<textarea v-model="field.labels" rows="4" maxlength="135" placeholder="每行一条，最多四条"></textarea></label>
    <label v-else-if="mode === 'summary'">概要文字<input v-model.trim="field.summary" maxlength="160" placeholder="概括选中分支"></label>
    <label v-else-if="mode === 'frame'">外框标题<input v-model.trim="field.frame" maxlength="160" placeholder="可留空"></label>
    <template v-else-if="mode === 'hyperlink'">
      <label>网址<input v-model="field.url" type="url" maxlength="2048" placeholder="https://"></label>
      <label>显示名称<input v-model="field.label" maxlength="160"></label>
      <a v-if="node.hyperlink" class="text-link" :href="node.hyperlink.url" target="_blank" rel="noopener noreferrer">打开当前链接</a>
    </template>
    <label v-else-if="mode === 'icon'">节点图标<select v-model="field.icon"><option value="">无</option><option v-for="(label, key) in iconChoices" :key="key" :value="key">{{ label }}</option></select></label>
    <template v-else-if="mode === 'image'">
      <label>本地图片<input type="file" accept="image/png,image/jpeg,image/webp,image/gif" @change="chooseImage"></label>
      <img v-if="field.image || node.image" class="map-node-image" :src="(field.image || node.image).data_url" alt="节点图片预览">
    </template>
    <template v-else-if="mode === 'formula'">
      <label>LaTeX 公式<textarea v-model="field.formula" rows="3" maxlength="1000" placeholder="例如 \frac{a}{b}"></textarea></label>
      <div v-if="formulaHtml" class="map-formula-preview" aria-label="公式预览" v-html="formulaHtml" />
    </template>
    <template v-else-if="mode === 'table'">
      <div class="map-table-scroll">
        <table class="map-node-table" aria-label="节点表格"><tbody><tr v-for="(row, y) in field.rows" :key="y">
          <td v-for="(_, x) in row" :key="x"><input v-model="row[x]" :aria-label="`第 ${y + 1} 行第 ${x + 1} 列`" maxlength="160"></td>
        </tr></tbody></table>
      </div>
      <div class="actions">
        <button class="button secondary" type="button" :disabled="field.rows.length >= 16" @click="field.rows.push(field.rows[0].map(() => ''))">增加行</button>
        <button class="button subtle" type="button" :disabled="field.rows.length <= 1" @click="field.rows.pop()">删末行</button>
        <button class="button secondary" type="button" :disabled="field.rows[0].length >= 8" @click="field.rows.forEach((row) => row.push(''))">增加列</button>
        <button class="button subtle" type="button" :disabled="field.rows[0].length <= 1" @click="field.rows.forEach((row) => row.pop())">删末列</button>
      </div>
    </template>
    <label v-else-if="mode === 'code'">代码块<textarea v-model="field.code" class="map-code-input" rows="9" maxlength="4000" spellcheck="false"></textarea></label>
    <template v-else-if="mode === 'nodeLinks'">
      <div v-for="target in linked" :key="target.id" class="section-heading">
        <button class="button subtle" type="button" @click="emit('jump', target.id)">{{ target.text }}</button>
        <button class="button subtle danger-text" type="button" @click="emit('unlink', target.id)">解除</button>
      </div>
      <label>关联本图主题<select v-model="field.target" :disabled="!targets.length">
        <option value="">选择主题</option><option v-for="target in targets" :key="target.id" :value="target.id">{{ target.text }}</option>
      </select></label>
    </template>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="dialog-actions">
      <button v-if="['image', 'table', 'frame'].includes(mode) && node[mode]" class="button subtle danger-text" type="button" @click="remove">移除</button>
      <button class="button secondary" type="button" @click="emit('cancel')">取消</button>
      <button class="button primary" type="submit" :disabled="reading || (mode === 'image' && !field.image) || (mode === 'nodeLinks' && !field.target)">
        {{ reading ? '正在处理' : mode === 'nodeLinks' ? '建立链接' : '保存' }}
      </button>
    </div>
  </form>
</template>
