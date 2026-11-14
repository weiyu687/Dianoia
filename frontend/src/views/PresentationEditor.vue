<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, ArrowUp, BarChart3, Copy, Download, FileImage, Play, Plus, Redo2, Save, Shapes, Sigma, Sparkles, Table2, Trash2, Type, Undo2, X } from 'lucide-vue-next'
import { api, download } from '../api'
import Modal from '../components/Modal.vue'
import MapSources from '../components/MapSources.vue'
import PdfViewer from '../components/PdfViewer.vue'
import SlideCanvas from '../components/SlideCanvas.vue'
import SlideInspector from '../components/SlideInspector.vue'
import SlideThumbnail from '../components/SlideThumbnail.vue'
import { clone, height, layouts, newElement, newSlide, readableInk, shapes, slideTitle, uid, width } from '../presentation'
import '../presentations.css'

const route = useRoute()
const router = useRouter()
const FormulaEditor = defineAsyncComponent(() => import('../components/FormulaEditor.vue'))
const endpoint = '/presentations/' + route.params.id
const row = ref(null)
const history = shallowRef([])
const future = shallowRef([])
const active = ref('')
const selected = ref([])
const fileInput = ref(null)
const dragPage = ref('')
const nextLayout = ref('body')
const nextShape = ref('rect')
const zoom = ref(1)
const notes = ref('')
const references = ref([])
const modal = ref(null)
const pdf = ref(false)
const pdfPage = ref(1)
const play = ref(false)
const playIndex = ref(0)
const playSurface = ref(null)
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const formError = ref('')
const dirty = ref(false)
let clipboard = []
let replacingImage
const document = computed(() => row.value?.document)
const page = computed(() => document.value?.slides.find((slide) => slide.id === active.value))
const item = computed(() => selected.value.length === 1 ? page.value?.elements.find((object) => object.id === selected.value[0]) : null)
const pageNumber = computed(() => document.value.slides.findIndex((slide) => slide.id === active.value) + 1)
const citeNames = computed(() => Object.fromEntries(references.value.map((resource) => [resource.id, resource.title])))
const snapshot = () => ({ title: row.value.title, document: clone(document.value), active: active.value })

onMounted(async () => {
  window.addEventListener('keydown', shortcuts)
  window.addEventListener('beforeunload', leave)
  try {
    row.value = await api(endpoint)
    const requested = Number(route.query.page) - 1
    activate((document.value.slides[requested] || document.value.slides[0]).id)
    references.value = (await api('/resources?course_id=' + row.value.course_id)).filter((resource) => resource.status === 'ready')
    if (typeof route.query.candidate === 'string') {
      const proposal = await api(endpoint + '/suggestions/' + encodeURIComponent(route.query.candidate))
      activate(proposal.request.slide_id)
      if (proposal.request.element_id) select(proposal.request.element_id)
      openDialog('AI')
      Object.assign(modal.value, { mode: proposal.request.mode, instruction: proposal.request.instruction,
        target: proposal.request.slide_id, element: proposal.request.element_id, candidate: proposal.result })
      router.replace({ query: { page: pageNumber.value } })
    }
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})
onUnmounted(() => {
  window.removeEventListener('keydown', shortcuts)
  window.removeEventListener('beforeunload', leave)
})
onBeforeRouteLeave(() => !dirty.value || window.confirm('课件有未保存的修改，确定离开？'))
function leave(event) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }

function activate(id) {
  active.value = id
  selected.value = []
  notes.value = page.value?.notes || ''
}
function change(operation) {
  if (busy.value) return
  const before = snapshot()
  operation()
  history.value = [...history.value.slice(-29), before]
  future.value = []
  dirty.value = true
}
function restore(state) {
  row.value.title = state.title
  row.value.document = state.document
  activate(state.active)
  dirty.value = true
}
function undo() {
  if (!history.value.length) return
  future.value = [...future.value, snapshot()]
  restore(history.value.at(-1))
  history.value = history.value.slice(0, -1)
}
function redo() {
  if (!future.value.length) return
  history.value = [...history.value, snapshot()]
  restore(future.value.at(-1))
  future.value = future.value.slice(0, -1)
}
function commitNotes() {
  if (page.value && notes.value !== page.value.notes) change(() => { page.value.notes = notes.value })
}
function titleChanged(event) { change(() => { row.value.title = event.target.value.trim() }) }
function pickPage(id) { commitNotes(); activate(id) }
function select(id, additive = false) {
  const target = page.value?.elements.find((entry) => entry.id === id)
  if (!target) { selected.value = []; return }
  const ids = target.group ? page.value.elements.filter((entry) => entry.group === target.group).map((entry) => entry.id) : [id]
  if (!additive) {
    if (!selected.value.includes(id)) selected.value = ids
  } else if (selected.value.includes(id)) {
    selected.value = selected.value.filter((entry) => !ids.includes(entry))
  } else selected.value = [...new Set([...selected.value, ...ids])]
}
function addSlide() {
  if (document.value.slides.length >= 80) return
  commitNotes()
  const slide = newSlide(nextLayout.value)
  change(() => { document.value.slides.splice(pageNumber.value, 0, slide); activate(slide.id) })
}
function duplicateSlide() {
  if (document.value.slides.length >= 80) return
  commitNotes()
  const slide = { ...clone(page.value), id: uid() }
  change(() => { document.value.slides.splice(pageNumber.value, 0, slide); activate(slide.id) })
}
function removeSlide() {
  if (document.value.slides.length < 2) return
  const index = pageNumber.value - 1
  change(() => {
    document.value.slides.splice(index, 1)
    activate(document.value.slides[Math.min(index, document.value.slides.length - 1)].id)
  })
}
function movePage(from, to) {
  if (from < 0 || to < 0 || from === to || to >= document.value.slides.length) return
  commitNotes()
  change(() => {
    const [slide] = document.value.slides.splice(from, 1)
    document.value.slides.splice(to, 0, slide)
  })
}
function dropPage(index) {
  movePage(document.value.slides.findIndex((slide) => slide.id === dragPage.value), index)
  dragPage.value = ''
}
function addObject(kind, fields) {
  if (page.value.elements.length >= 100) return
  const object = newElement(kind, fields)
  change(() => { page.value.elements.push(object); selected.value = [object.id] })
}
function setItem(fields) { if (item.value) change(() => Object.assign(item.value, fields)) }
function setPositions(positions) {
  const affected = page.value.elements.filter((object) => !object.locked && positions.some((position) => position.id === object.id))
  if (!affected.length) return
  change(() => {
    for (const object of affected) {
      const { id, ...position } = positions.find((entry) => entry.id === object.id)
      if (position.x !== undefined) position.x = Math.min(width * 2, Math.max(-width, position.x))
      if (position.y !== undefined) position.y = Math.min(height * 2, Math.max(-height, position.y))
      Object.assign(object, position)
    }
  })
}
function deleteSelection() {
  if (!selected.value.length) return
  change(() => {
    page.value.elements = page.value.elements.filter((object) => object.locked || !selected.value.includes(object.id))
    selected.value = []
  })
}
function rearrange(mode) {
  const elements = page.value.elements
  const index = elements.findIndex((object) => object.id === item.value?.id)
  if (index < 0) return
  const end = elements.length - 1
  const next = { front: end, back: 0, up: Math.min(index + 1, end), down: Math.max(0, index - 1) }[mode]
  if (next !== index) change(() => { elements.splice(next, 0, elements.splice(index, 1)[0]) })
}
function organize(unset = false) {
  const group = unset ? null : uid()
  change(() => {
    for (const object of page.value.elements) if (selected.value.includes(object.id) && !object.locked) object.group = group
  })
}
function alignSelection(mode, canvas = false) {
  const objects = page.value.elements.filter((object) => selected.value.includes(object.id) && !object.locked)
  if (objects.length < (canvas ? 1 : 2)) return
  const left = canvas ? 0 : Math.min(...objects.map((object) => object.x))
  const right = canvas ? width : Math.max(...objects.map((object) => object.x + object.width))
  const top = canvas ? 0 : Math.min(...objects.map((object) => object.y))
  const bottom = canvas ? height : Math.max(...objects.map((object) => object.y + object.height))
  if (mode === 'distribute' || mode === 'distributeVertical') {
    const horizontal = mode === 'distribute'
    const coordinate = horizontal ? 'x' : 'y'
    const dimension = horizontal ? 'width' : 'height'
    const start = horizontal ? left : top
    const end = horizontal ? right : bottom
    const ordered = [...objects].sort((a, b) => a[coordinate] - b[coordinate])
    const gap = (end - start - ordered.reduce((sum, object) => sum + object[dimension], 0)) / (ordered.length - 1)
    let cursor = start
    setPositions(ordered.map((object) => {
      const position = { id: object.id, [coordinate]: cursor }
      cursor += object[dimension] + gap
      return position
    }))
  } else setPositions(objects.map((object) => ({ id: object.id, ...{
    left: { x: left }, top: { y: top }, center: { x: (left + right - object.width) / 2 },
    right: { x: right - object.width }, bottom: { y: bottom - object.height },
    middle: { y: (top + bottom - object.height) / 2 },
  }[mode] })))
}
function duplicateObjects(objects) {
  const groups = new Map()
  const copies = clone(objects).slice(0, 100 - page.value.elements.length).map((object) => {
    if (object.group && !groups.has(object.group)) groups.set(object.group, uid())
    return { ...object, id: uid(), group: groups.get(object.group) || null, locked: false,
      x: Math.min(1920, object.x + 20), y: Math.min(1080, object.y + 20) }
  })
  if (!copies.length) return
  change(() => { page.value.elements.push(...copies); selected.value = copies.map((object) => object.id) })
}
function openImage(id) { replacingImage = id; fileInput.value.click() }
async function loadImage(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  error.value = ''
  if (!['image/png', 'image/jpeg'].includes(file.type) || file.size > 1_000_000) {
    error.value = '请选择 1 MB 以内的 PNG 或 JPEG 图片'
    return
  }
  const targetPage = active.value, id = replacingImage
  try {
    const image = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onerror = reject
      reader.onload = () => resolve(reader.result)
      reader.readAsDataURL(file)
    })
    const bitmap = new Image()
    bitmap.src = image
    await bitmap.decode()
    if (bitmap.naturalWidth * bitmap.naturalHeight > 6_000_000) throw new Error('图片像素超过 600 万')
    if (active.value !== targetPage) return
    const target = page.value.elements.find((object) => object.id === id)
    if (target) change(() => { target.image = image })
    else {
      const w = Math.min(480, bitmap.naturalWidth, 330 * bitmap.naturalWidth / bitmap.naturalHeight)
      addObject('image', { image, width: Math.max(8, w), height: Math.max(8, w * bitmap.naturalHeight / bitmap.naturalWidth) })
    }
  } catch (failure) { error.value = failure.message || '无法打开图片' }
}
function editContent(id) {
  const target = page.value.elements.find((object) => object.id === id)
  if (!target || target.locked) return
  if (target.kind === 'image') { openImage(id); return }
  if (target.kind === 'formula') { openFormula(target); return }
  if (target.kind === 'shape') return
  formError.value = ''
  modal.value = { type: 'element', item: clone(target) }
  nextTick(() => window.document.querySelector('.presentation-text-input')?.focus())
}
function openFormula(target = null) {
  formError.value = ''
  modal.value = { type: 'formula', item: target }
}
async function applyFormula(latex) {
  const target = modal.value.item
  formError.value = ''
  busy.value = true
  try {
    await api(endpoint + '/formula', { method: 'POST', body: { latex } })
  } catch (failure) {
    formError.value = failure.message
    return
  } finally { busy.value = false }
  if (target) change(() => { target.latex = latex })
  else addObject('formula', { latex, x: 76, y: page.value.layout === 'cover' ? 375 : 205,
    width: 620, height: 138, size: 29, color: readableInk(page.value.background) })
  modal.value = null
}
function resizeTable(axis, delta) {
  const rows = modal.value.item.rows
  if (axis === 'row' && delta > 0 && rows.length < 14) rows.push(rows[0].map(() => ''))
  if (axis === 'row' && delta < 0 && rows.length > 1) rows.pop()
  if (axis === 'column' && delta > 0 && rows[0].length < 10) rows.forEach((row) => row.push(''))
  if (axis === 'column' && delta < 0 && rows[0].length > 1) rows.forEach((row) => row.pop())
}
function openDialog(type) {
  formError.value = ''
  modal.value = { type, title: row.value.title + '模板', layout_only: false, references: clone(type === 'cite' ? page.value.citations : document.value.sources),
    mode: item.value?.kind === 'text' && !item.value.locked ? 'text' : 'page', instruction: '', candidate: null }
}
async function save() {
  if (busy.value || !row.value) return false
  commitNotes()
  if (!dirty.value) return true
  if (!row.value.title.trim()) { error.value = '请填写课件名称'; return false }
  busy.value = true
  error.value = ''
  try {
    const current = snapshot()
    const result = await api(endpoint, { method: 'PUT', body: {
      title: current.title, document: current.document, revision: row.value.revision,
    } })
    row.value.revision = result.revision
    row.value.updated_at = result.updated_at
    dirty.value = JSON.stringify(snapshot().document) !== JSON.stringify(current.document) || row.value.title !== current.title || notes.value !== page.value.notes
    return !dirty.value
  } catch (failure) { error.value = failure.message; return false }
  finally { busy.value = false }
}
async function exportFile(format) {
  if (!await save()) return
  busy.value = true
  try { await download(endpoint + '/export/' + format, row.value.title + '.' + format) }
  catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
async function preview() {
  if (!await save()) return
  pdfPage.value = pageNumber.value
  pdf.value = true
}
async function suggest() {
  const form = modal.value
  if (busy.value || !await save()) return
  busy.value = true
  formError.value = ''
  try {
    form.target = page.value.id
    form.element = item.value?.id
    form.candidate = await api(endpoint + '/suggest', { method: 'POST', body: {
      revision: row.value.revision, mode: form.mode, instruction: form.instruction, slide_id: form.target, element_id: form.element,
    } })
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}
function adopt() {
  const form = modal.value
  if (!form.candidate || form.candidate.revision !== row.value.revision || form.target !== active.value || dirty.value) {
    formError.value = '当前页已有变化，请重新生成候选'
    return
  }
  if (form.mode === 'insert' && document.value.slides.length >= 80) { formError.value = '课件已达到 80 页'; return }
  change(() => {
    if (form.mode === 'page') {
      document.value.slides[pageNumber.value - 1] = { ...form.candidate.slide, id: active.value }
      activate(active.value)
    } else if (form.mode === 'insert') {
      document.value.slides.splice(pageNumber.value, 0, form.candidate.slide)
      activate(form.candidate.slide.id)
    } else if (form.mode === 'notes') {
      page.value.notes = notes.value = form.candidate.text
    } else {
      const object = page.value.elements.find((object) => object.id === form.element)
      if (object && !object.locked) object.text = form.candidate.text
    }
  })
  modal.value = null
}
async function saveDialog() {
  const form = modal.value
  if (form.type === 'element') {
    const target = page.value.elements.find((object) => object.id === form.item.id)
    if (!target || target.locked) return
    if (form.item.kind === 'chart' && !form.item.values.some((value) => value > 0)) { formError.value = '至少需要一个大于 0 的数据'; return }
    change(() => Object.assign(target, form.item))
  } else if (form.type === 'sources' || form.type === 'cite') {
    const sources = form.type === 'sources' ? form.references : document.value.sources
    const fits = (citation) => sources.some((source) => source.resource_id === citation.resource_id &&
      source.start <= citation.start && citation.start <= citation.end && citation.end <= source.end)
    if (form.type === 'cite' && !form.references.every(fits)) { formError.value = '引用必须位于已挂载的资料范围内'; return }
    change(() => {
      if (form.type === 'cite') page.value.citations = form.references
      else {
        document.value.sources = form.references
        for (const slide of document.value.slides) slide.citations = slide.citations.filter(fits)
      }
    })
  } else if (form.type === 'template') {
    if (!await save()) return
    busy.value = true
    try {
      await api(endpoint + '/template', { method: 'POST', body: {
        title: form.title, layout_only: form.layout_only, revision: row.value.revision,
      } })
    } catch (failure) { formError.value = failure.message; return }
    finally { busy.value = false }
  }
  modal.value = null
}
function startPlay() {
  playIndex.value = pageNumber.value - 1
  play.value = true
  nextTick(() => playSurface.value?.focus())
}
function step(delta) { playIndex.value = Math.max(0, Math.min(document.value.slides.length - 1, playIndex.value + delta)) }
function shortcuts(event) {
  if (!page.value || event.isComposing) return
  if (play.value) {
    if (event.key === 'Escape') play.value = false
    if (['ArrowRight','ArrowDown','PageDown',' '].includes(event.key)) { event.preventDefault(); step(1) }
    if (['ArrowLeft','ArrowUp','PageUp'].includes(event.key)) { event.preventDefault(); step(-1) }
    return
  }
  if (modal.value || pdf.value || busy.value || event.target.closest?.('input, textarea, select, [contenteditable]')) return
  const primary = event.ctrlKey || event.metaKey
  const key = event.key.toLowerCase()
  if (primary && key === 's') { event.preventDefault(); save() }
  else if (primary && key === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo() }
  else if (primary && key === 'y') { event.preventDefault(); redo() }
  else if (primary && key === 'a') { event.preventDefault(); selected.value = page.value.elements.map((object) => object.id) }
  else if (primary && ['c','d','v'].includes(key)) {
    const objects = page.value.elements.filter((object) => selected.value.includes(object.id))
    if (objects.length || (key === 'v' && clipboard.length)) {
      event.preventDefault()
      if (key === 'c') clipboard = clone(objects)
      else duplicateObjects(key === 'v' ? clipboard : objects)
    }
  } else if (['delete','backspace'].includes(key) && selected.value.length) { event.preventDefault(); deleteSelection() }
  else if (key.startsWith('arrow') && selected.value.length) {
    const delta = event.shiftKey ? 10 : 1
    const dx = key === 'arrowleft' ? -delta : key === 'arrowright' ? delta : 0
    const dy = key === 'arrowup' ? -delta : key === 'arrowdown' ? delta : 0
    event.preventDefault()
    setPositions(page.value.elements.filter((object) => selected.value.includes(object.id)).map((object) =>
      ({ id: object.id, x: object.x + dx, y: object.y + dy })))
  }
}
</script>

<template>
  <div class="page presentation-editor">
    <RouterLink class="text-link back-link" to="/presentations"><ArrowLeft :size="16" /> 演示文稿</RouterLink>
    <p v-if="loading" class="empty-state" role="status">正在加载课件</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <template v-if="row && page">
      <header class="page-heading presentation-heading">
        <div class="editor-title">
          <input :value="row.title" aria-label="课件名称" maxlength="160" :disabled="busy" @change="titleChanged">
          <p role="status">v{{ row.revision }} · {{ dirty ? '有未保存的修改' : '已保存' }}</p>
        </div>
        <div class="actions">
          <button class="button secondary" :disabled="busy" @click="openDialog('sources')">参考资料</button>
          <button class="button secondary" :disabled="busy" @click="openDialog('template')">存为模板</button>
          <button class="button secondary" :disabled="busy" @click="preview">PDF 预览</button>
          <button class="button secondary" :disabled="busy" @click="exportFile('pptx')"><Download :size="16" /> PPTX</button>
          <button class="button secondary" :disabled="busy" @click="startPlay"><Play :size="16" /> 放映</button>
          <button class="button primary" :disabled="busy || !dirty" @click="save"><Save :size="16" /> 保存</button>
        </div>
      </header>
      <div v-if="pdf" class="stack">
        <div class="actions"><button class="button secondary" @click="pdf = false">返回编辑</button>
          <button class="button secondary" :disabled="busy" @click="exportFile('pdf')"><Download :size="16" /> 下载 PDF</button></div>
        <PdfViewer :src="'/api' + endpoint + '/export/pdf?inline=true&v=' + row.revision" v-model:page="pdfPage" />
      </div>
      <div v-else class="presentation-workspace panel" :inert="busy">
        <div class="presentation-toolbar">
          <div class="presentation-toolgroup">
            <button class="button subtle icon-only" aria-label="撤销" title="撤销" :disabled="!history.length" @click="undo"><Undo2 :size="17" /></button>
            <button class="button subtle icon-only" aria-label="重做" title="重做" :disabled="!future.length" @click="redo"><Redo2 :size="17" /></button>
          </div>
          <div class="presentation-toolgroup">
            <button class="button subtle" @click="addObject('text', { color: readableInk(page.background) })"><Type :size="16" /> 文本</button>
            <button class="button subtle" @click="addObject('shape',{shape:nextShape})"><Shapes :size="16" /> 形状</button>
            <select v-model="nextShape" aria-label="插入形状"><option v-for="(label, key) in shapes" :key="key" :value="key">{{ label }}</option></select>
            <button class="button subtle" @click="openImage(null)"><FileImage :size="16" /> 图片</button>
            <button class="button subtle" @click="addObject('table')"><Table2 :size="16" /> 表格</button>
            <button class="button subtle" @click="addObject('chart', { color: readableInk(page.background) })"><BarChart3 :size="16" /> 图表</button>
            <button class="button subtle" @click="openFormula()"><Sigma :size="16" /> 公式</button>
          </div>
          <div class="presentation-toolgroup"><button class="button subtle" @click="openDialog('AI')"><Sparkles :size="17" /> AI 局部生成</button></div>
        </div>
        <aside class="presentation-pages">
          <div class="presentation-page-tools">
            <button class="button secondary icon-only" aria-label="新建幻灯片" title="新建幻灯片" @click="addSlide"><Plus :size="19" /></button>
            <select v-model="nextLayout" aria-label="新页面版式"><option v-for="(name,key) in layouts" :key="key" :value="key">{{ name }}</option></select>
          </div>
          <div class="presentation-page-list">
            <button v-for="(slide,index) in document.slides" :key="slide.id" class="presentation-page-tile"
              :aria-pressed="slide.id === active" :aria-label="'第 ' + (index + 1) + ' 页 ' + slideTitle(slide)" draggable="true"
              @dragstart="dragPage = slide.id; $event.dataTransfer.setData('text/plain',slide.id)" @dragover.prevent @drop.prevent="dropPage(index)" @click="pickPage(slide.id)">
              <SlideThumbnail :slide="slide" /><span>{{ index + 1 }} · {{ slideTitle(slide) }}</span>
            </button>
          </div>
          <div class="presentation-toolgroup presentation-page-footer">
            <button class="button subtle icon-only" aria-label="复制页面" title="复制页面" @click="duplicateSlide"><Copy :size="15" /></button>
            <button class="button subtle icon-only" aria-label="页面上移" :disabled="pageNumber === 1" @click="movePage(pageNumber-1,pageNumber-2)"><ArrowUp :size="15" /></button>
            <button class="button subtle icon-only" aria-label="页面下移" :disabled="pageNumber === document.slides.length" @click="movePage(pageNumber-1,pageNumber)"><ArrowDown :size="15" /></button>
            <button class="button subtle icon-only danger-text" aria-label="删除页面" :disabled="document.slides.length === 1" @click="removeSlide"><Trash2 :size="15" /></button>
          </div>
        </aside>
        <section class="presentation-center" aria-label="课件画布">
          <SlideCanvas :slide="page" :selected="selected" :zoom="zoom" editable @select="select" @edit="editContent" @move="setPositions" @transform="setPositions" />
          <div class="presentation-workspace-status"><span>第 {{ pageNumber }} 页 / {{ document.slides.length }}</span>
            <button class="button subtle" @click="openDialog('cite')">本页引用<template v-if="page.citations.length"> · {{ page.citations.length }}</template></button>
            <label>缩放<select v-model.number="zoom"><option :value=".75">75%</option><option :value="1">适应画布</option><option :value="1.25">125%</option><option :value="1.5">150%</option></select></label>
          </div>
          <div v-if="page.citations.length" class="presentation-citations">
            <RouterLink v-for="(source,index) in page.citations" :key="index" class="text-link"
              :to="{ name:'resource', params:{id:source.resource_id}, query:{page:source.start} }">
              {{ citeNames[source.resource_id] || '资料已不可用' }} · {{ source.start }}<template v-if="source.end !== source.start">–{{ source.end }}</template> 页
            </RouterLink>
          </div>
          <label class="presentation-notes">讲者备注<textarea v-model="notes" rows="3" maxlength="8000" @input="dirty = true" @blur="commitNotes" /></label>
        </section>
        <SlideInspector :slide="page" :item="item" :selected="selected" @change="setItem" @select="select" @edit="editContent" @align="alignSelection"
          @background="change(() => page.background = $event)" @delete="deleteSelection" @layer="rearrange" @group="organize()" @ungroup="organize(true)" />
      </div>
      <input ref="fileInput" type="file" accept="image/png,image/jpeg" hidden @change="loadImage">
      <Teleport to="body">
        <div v-if="play" class="presentation-player" role="dialog" aria-modal="true" aria-label="放映">
          <button ref="playSurface" type="button" class="presentation-play-surface" aria-label="点击画面翻到下一页" @click="step(1)">
            <SlideCanvas :slide="document.slides[playIndex]" />
          </button>
          <div class="presentation-play-controls"><button class="button secondary" :disabled="!playIndex" @click="step(-1)">上一页</button>
            <span>{{ playIndex + 1 }} / {{ document.slides.length }}</span>
            <button class="button secondary" :disabled="playIndex === document.slides.length-1" @click="step(1)">下一页</button>
            <button class="button secondary icon-only" aria-label="退出放映" @click="play = false"><X :size="18" /></button></div>
        </div>
      </Teleport>
    </template>
    <Modal :open="!!modal" :title="{ element:'编辑内容', sources:'课件参考资料', cite:'本页引用', template:'存为模板', AI:'AI 局部生成', formula:'课件公式' }[modal?.type]"
      wide @close="!busy && (modal = null)">
      <template v-if="modal?.type === 'formula'">
        <FormulaEditor :initial="modal.item?.latex || ''" :replace="!!modal.item" :busy="busy" @apply="applyFormula" />
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      </template>
      <form v-else-if="modal" class="stack" @submit.prevent="modal.type === 'AI' ? suggest() : saveDialog()">
        <template v-if="modal.type === 'element'">
          <label v-if="modal.item.kind === 'text'">文本框内容<textarea v-model="modal.item.text" rows="7" maxlength="4000" class="presentation-text-input" /></label>
          <template v-else-if="modal.item.kind === 'table'">
            <div class="presentation-control-row">
              <button type="button" class="button secondary" @click="resizeTable('row',1)">增加行</button><button type="button" class="button secondary" @click="resizeTable('row',-1)">删末行</button>
              <button type="button" class="button secondary" @click="resizeTable('column',1)">增加列</button><button type="button" class="button secondary" @click="resizeTable('column',-1)">删末列</button>
            </div>
            <div class="table-scroll"><table class="presentation-data-edit"><tbody>
              <tr v-for="(cells,r) in modal.item.rows" :key="r"><td v-for="(_,c) in cells" :key="c"><input v-model="cells[c]" maxlength="160" :aria-label="'第'+(r+1)+'行第'+(c+1)+'列'"></td></tr>
            </tbody></table></div>
          </template>
          <template v-else>
            <div v-for="(_, index) in modal.item.labels" :key="index" class="presentation-form-cols">
              <label>类别 {{ index + 1 }}<input v-model="modal.item.labels[index]" maxlength="160" required></label>
              <label>数值 {{ index + 1 }}<input v-model.number="modal.item.values[index]" min="0" max="1000000000000" type="number" step="any" required></label>
            </div>
            <div class="presentation-control-row">
              <button type="button" class="button secondary" :disabled="modal.item.labels.length >= 16" @click="modal.item.labels.push('新类别'); modal.item.values.push(1)">增加类别</button>
              <button type="button" class="button secondary" :disabled="modal.item.labels.length <= 1" @click="modal.item.labels.pop(); modal.item.values.pop()">删末项</button>
            </div>
          </template>
        </template>
        <MapSources v-else-if="modal.type === 'sources' || modal.type === 'cite'" v-model="modal.references"
          :resources="modal.type === 'cite' ? references.filter((resource) => document.sources.some((source) => source.resource_id === resource.id)) : references" />
        <template v-else-if="modal.type === 'template'">
          <label>模板名称<input v-model.trim="modal.title" maxlength="160" required></label>
          <label class="presentation-checkbox"><input v-model="modal.layout_only" type="checkbox">只保留版式</label>
        </template>
        <template v-else>
          <label>修改范围<select v-model="modal.mode" :disabled="busy" @change="modal.candidate = null"><option value="page">重新生成本页</option>
            <option value="text" :disabled="item?.kind !== 'text' || item.locked">选中文本框</option><option value="notes">讲者备注</option>
            <option value="insert" :disabled="document.slides.length >= 80">在本页后插入一页</option></select></label>
          <label>补充要求<textarea v-model.trim="modal.instruction" rows="3" maxlength="1200" :disabled="busy" @input="modal.candidate = null" /></label>
          <SlideThumbnail v-if="modal.candidate?.slide" :slide="modal.candidate.slide" />
          <div v-else-if="modal.candidate" class="panel presentation-candidate">{{ modal.candidate.text }}</div>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions">
          <button v-if="modal.type === 'AI' && modal.candidate" type="button" class="button primary" :disabled="busy" @click="adopt">采纳候选</button>
          <button type="submit" :class="['button',modal.candidate ? 'secondary' : 'primary']" :disabled="busy">{{ busy ? '处理中…' : modal.type === 'AI' ? '生成候选' : '确定' }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
