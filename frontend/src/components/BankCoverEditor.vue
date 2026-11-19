<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Upload } from 'lucide-vue-next'
import { api } from '../api'
import { clone } from '../questionBanks'
import BankCover from './BankCover.vue'
const props = defineProps({ bank: Object, course: String, themes: Array, busy: Boolean })
const emit = defineEmits(['apply'])
const cover = ref(clone(props.bank.cover))
const source = ref(null)
const zoom = ref(1)
const center = ref({ x: .5, y: .5 })
const error = ref('')
const uploading = ref(false)
const area = ref(null)
let drag = null
const crop = computed(() => {
  if (!source.value) return null
  const ratio = source.value.width / source.value.height
  const width = (ratio >= 16/9 ? (16/9)/ratio : 1) / zoom.value
  const height = (ratio >= 16/9 ? 1 : ratio/(16/9)) / zoom.value
  return { width, height, x: Math.max(0, Math.min(1-width,center.value.x-width/2)), y: Math.max(0,Math.min(1-height,center.value.y-height/2)) }
})
function chooseTheme(theme) { cover.value = { ...cover.value, theme: theme.id, accent: theme.accent, asset_id: null }; clearSource() }
function clearSource() { if (source.value) URL.revokeObjectURL(source.value.url); source.value = null }
async function selectFile(file) {
  error.value = ''
  if (!file) return
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 5*1024*1024) { error.value = '请选择 5 MB 内的 JPG、PNG 或 WebP 图片'; return }
  const url = URL.createObjectURL(file)
  const image = new Image()
  try {
    await new Promise((resolve,reject) => { image.onload = resolve; image.onerror = reject; image.src = url })
    if (image.naturalWidth * image.naturalHeight > 20000000) throw new Error('图片不能超过 2000 万像素')
    clearSource(); source.value = { url, file, width: image.naturalWidth, height: image.naturalHeight }; zoom.value = 1; center.value = { x:.5,y:.5 }
  } catch (failure) { URL.revokeObjectURL(url); error.value = failure.message || '无法读取图片' }
}
function down(event) { area.value.setPointerCapture(event.pointerId); drag = { x:event.clientX,y:event.clientY, center:{...center.value} } }
function move(event) {
  if (!drag || !crop.value) return
  const box = area.value.getBoundingClientRect()
  center.value = { x:Math.max(crop.value.width/2, Math.min(1-crop.value.width/2,drag.center.x-(event.clientX-drag.x)/box.width*crop.value.width)),
    y:Math.max(crop.value.height/2, Math.min(1-crop.value.height/2,drag.center.y-(event.clientY-drag.y)/box.height*crop.value.height)) }
}
async function apply() {
  uploading.value = true; error.value = ''
  try {
    if (source.value) {
      const body = new FormData(); body.set('file',source.value.file); body.set('kind','cover')
      for (const [key,value] of Object.entries(crop.value)) body.set(key,String(value))
      const asset = await api(`/question-banks/${props.bank.id}/assets`, { method:'POST',body })
      cover.value.asset_id = asset.id
    }
    emit('apply',clone(cover.value))
  } catch (failure) { error.value = failure.message }
  finally { uploading.value = false }
}
onBeforeUnmount(clearSource)
</script>
<template>
  <div class="stack">
    <div class="bank-cover-options"><button v-for="theme in themes" :key="theme.id" type="button" :aria-pressed="cover.theme === theme.id && !cover.asset_id" @click="chooseTheme(theme)">
      <BankCover :bank="{title:bank.title,cover:{theme:theme.id,accent:theme.accent,layout:cover.layout}}" :course="course" /><span>{{ theme.name }}</span></button></div>
    <div v-if="source && crop" class="stack"><svg ref="area" class="bank-crop-area" viewBox="0 0 1200 675" @pointerdown="down" @pointermove="move" @pointerup="drag = null" @pointercancel="drag = null">
      <image :href="source.url" :x="-crop.x/crop.width*1200" :y="-crop.y/crop.height*675" :width="1200/crop.width" :height="675/crop.height" preserveAspectRatio="none" /></svg>
      <label>缩放图片，拖动调整裁剪位置<input v-model.number="zoom" type="range" min="1" max="3" step=".05"></label></div>
    <BankCover v-else :bank="{...bank,cover}" :course="course" />
    <div class="bank-fields"><label>强调色<input v-model="cover.accent" type="color"></label><label>标题布局<select v-model="cover.layout"><option value="left">左侧排版</option><option value="center">居中排版</option></select></label></div>
    <label class="button secondary"><Upload :size="16" /> 上传自己的封面<input class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" @change="selectFile($event.target.files[0])"></label>
    <p class="muted">16:9 · JPG / PNG / WebP · 最大 5 MB。标题和封面修改仅影响草稿，发布更新后学生才看到新版。</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button class="button primary" :disabled="busy || uploading" @click="apply">{{ busy || uploading ? '正在保存…' : '保存封面' }}</button>
  </div>
</template>
