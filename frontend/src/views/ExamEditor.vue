<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  DocxEditorContent, DocxEditorContentControl, DocxEditorContextMenu, DocxEditorHyperLink,
  DocxEditorLoading, DocxEditorOpenFailure, DocxEditorRoot, DocxEditorToolbar, DocxEditorUnsupportedElement,
  DocxEditorViewport, LocaleProvider,
} from '@docx-editor.dev/vue'
import { zhCN } from '@docx-editor.dev/i18n'
import { createBrowserAutomationHost } from '@docx-editor.dev/core/editor'
import { setHarfBuzzWasmUrl } from '@docx-editor.dev/core/layout'
import harfBuzzWasm from '@docx-editor.dev/core/harfbuzz.wasm?url'
import '@docx-editor.dev/vue/styles.css'
import { ArrowLeft, BookmarkPlus, Download, Eye, Save, Sparkles, Sigma } from 'lucide-vue-next'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { api, download } from '../api'
import AnswerSheetLayout from '../components/AnswerSheetLayout.vue'
import FormulaEditor from '../components/FormulaEditor.vue'
import MathPreview from '../components/MathPreview.vue'
import Modal from '../components/Modal.vue'
import MapSources from '../components/MapSources.vue'
import PdfViewer from '../components/PdfViewer.vue'
import { examKinds } from '../examKinds'
import { equationMarkup, equationPackage, mathSegments, MATH_NS } from '../examMath'
import { theme } from '../session'
import '../exam.css'

setHarfBuzzWasmUrl(harfBuzzWasm)

const id = String(useRoute().params.id)
const path = `/exams/${id}`
const exam = ref(null)
const bytes = shallowRef(null)
const editor = shallowRef(null)
const selected = ref('')
const selectionText = ref('')
const loading = ref(true)
const busy = ref(false)
const dirty = ref(false)
const error = ref('')
const formError = ref('')
const modal = ref('')
const meta = ref(null)
const formula = shallowRef(null)
const answerInput = ref(null)
const explanationInput = ref(null)
const equationSources = new Map()
const instruction = ref('')
const mode = ref('replace')
const candidate = ref(null)
const preview = ref('')
const editing = ref('paper')
const documentKey = ref(0)
const answerState = ref(null)
const sheetState = ref(null)
const sourceDraft = ref([])
const resources = ref([])
const page = ref(1)
const wordPage = ref(1)
const wordPages = ref(0)
const ready = computed(() => !!editor.value && !busy.value)
const active = computed(() => exam.value?.questions.find((question) => question.id === selected.value))
const fonts = { supportedFamilies: ['宋体', '黑体', '仿宋', '楷体', '微软雅黑', '等线', '华文中宋', '思源宋体'] }
const revisionModes = { replace: '重新出题', stem: '修改题干', options: '修改干扰项', difficulty: '调整难度' }
const documentLabels = { paper: '试卷', answers: '参考答案', sheet: '答题卡' }
const formats = { docx: 'Word (.docx)', doc: 'Word (.doc)', pdf: 'PDF', tex: 'LaTeX 源文件', 'latex-pdf': 'LaTeX PDF' }
const canPreview = computed(() => editing.value !== 'sheet' || sheetState.value?.saved)
let selectionUnsubscribe
let equationUnsubscribe
let changes = 0
let pendingExport = false

async function load(row) {
  const file = await api(`${path}/document?revision=${row.revision}`, { binary: true })
  bytes.value = await file.arrayBuffer()
  exam.value = row
  dirty.value = false
}

onMounted(async () => {
  window.addEventListener('beforeunload', beforeUnload)
  try { await load(await api(path)) }
  catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

onBeforeUnmount(() => {
  selectionUnsubscribe?.()
  equationUnsubscribe?.()
  window.removeEventListener('beforeunload', beforeUnload)
})

function beforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => !dirty.value || window.confirm('当前有未保存的文档修改，确定离开？'))

function updateSelection(clear = false) {
  const instance = editor.value
  if (!instance) return
  updatePage()
  selectionText.value = instance.query({ type: 'selectedText' }) || ''
  const mark = instance.query({ type: 'bookmarks' })?.find((entry) => entry.atSelection && entry.name.startsWith('dexam_'))
  if (mark && exam.value?.questions.some((question) => question.id === mark.name)) selected.value = mark.name
  else if (clear) selected.value = ''
}

function updatePage() {
  wordPage.value = editor.value?.getCurrentPage('viewport') || 1
  wordPages.value = editor.value?.getTotalPages() || 0
}

function jumpPage(event) {
  const input = event.currentTarget.elements.page
  const number = input.valueAsNumber
  if (Number.isInteger(number) && number >= 1 && number <= wordPages.value) editor.value?.scrollToPage(number)
  updatePage()
}

function editorReady(instance) {
  editor.value = instance
  selectionUnsubscribe?.()
  selectionUnsubscribe = instance.on('selectionChange', () => updateSelection())
  equationUnsubscribe?.()
  equationUnsubscribe = instance.setEquationChrome({
    onPopover: ({ equation }) => openWordFormula(equation),
  })
  updateSelection()
}

function isEquation(element) {
  return element.namespaceUri === MATH_NS && element.localName === 'oMath' && !!equationMarkup(element.source)
}

function openWordFormula(equation = null, source = '') {
  const instance = editor.value
  if (!instance || !ready.value || !instance.snapshot().editable || !!preview.value) return
  const surface = instance.surface
  if (!surface) return
  const selection = surface.state().selection
  if (equation) {
    const point = (offset) => ({ paragraphId: equation.paragraphId, offset })
    formula.value = { selection: { anchor: point(equation.start), head: point(equation.end) },
      word: true, replace: true, source: source || equationSources.get(equation.id) || simpleEquationSource(equation.linear) }
  } else {
    const text = instance.query({ type: 'selectedText' })?.trim() || ''
    const parts = mathSegments(text)
    formula.value = { selection, word: true, replace: false,
      source: parts.length === 1 && parts[0].math ? parts[0].text : '' }
  }
  formError.value = ''
  modal.value = 'formula'
}

function simpleEquationSource(linear) {
  return linear && /^[\p{L}\p{N}+\-=., ()/^_*]+$/u.test(linear) ? linear : ''
}

function rememberEquation(element) {
  const latex = equationMarkup(element.source)
  equationSources.set(element.nodeId, latex)
  return '\\(' + latex + '\\)'
}

function sizeEquation(element) {
  if (!element) return
  requestAnimationFrame(() => {
    const atom = element.closest('[data-docx-equation]')
    const visual = element.querySelector('.katex-html .base')
    if (!atom || !visual) return
    const observer = new ResizeObserver(() => {
      const bases = [...element.querySelectorAll('.katex-html .base')]
      const width = Math.ceil(bases.reduce((total, base) => total + base.offsetWidth, 0)) + 3
      const height = Math.max(...bases.map((base) => {
        const vertical = [...base.querySelectorAll('.vlist')].reduce((maximum, item) => Math.max(maximum, item.offsetHeight), 0)
        return Math.max(base.offsetHeight, vertical * 1.8)
      })) + 3
      const fallback = element.parentElement
      const line = atom.closest('.docx-line')
      const lineHeight = line?.offsetHeight || 0
      atom.style.width = width + 'px'
      atom.style.height = height + 'px'
      if (fallback) Object.assign(fallback.style, { width: width + 'px', height: height + 'px', overflow: 'visible' })
      if (height > lineHeight) atom.style.verticalAlign = 'middle'
    })
    observer.observe(visual)
    formulaObservers.get(element)?.disconnect()
    formulaObservers.set(element, observer)
  })
}

const formulaObservers = new Map()
const vEquationBox = {
  mounted: sizeEquation,
  updated: sizeEquation,
  unmounted(element) {
    formulaObservers.get(element)?.disconnect()
    formulaObservers.delete(element)
  },
}

function equationFromAtom(atom) {
  return { id: atom.dataset.docxEquation, paragraphId: atom.dataset.paragraphId,
    start: Number(atom.dataset.start), end: Number(atom.dataset.end) }
}

function openPreviewEquation(element, event) {
  const atom = event.currentTarget.closest('[data-docx-equation]')
  if (atom) openWordFormula(equationFromAtom(atom), equationMarkup(element.source))
}

function onEquationClick(event) {
  const atom = event.target.closest?.('[data-docx-equation]')
  if (!atom || !equationSources.has(atom.dataset.docxEquation)) return
  event.preventDefault()
  event.stopPropagation()
  openWordFormula(equationFromAtom(atom))
}

function openTextFormula(key) {
  const input = key === 'answer' ? answerInput.value : explanationInput.value
  const { selectionStart: start, selectionEnd: end } = input
  const value = meta.value[key]
  let offset = 0
  let matched
  for (const part of mathSegments(value)) {
    const length = (part.original || part.text).length
    if (part.math && start >= offset && end <= offset + length) {
      matched = { start: offset, end: offset + length, source: part.text }
      break
    }
    offset += length
  }
  formula.value = { key, start, end, source: '', ...matched, replace: !!matched }
  formError.value = ''
  modal.value = 'formula'
}

function closeFormula() {
  const target = formula.value
  formula.value = null
  formError.value = ''
  modal.value = target?.word ? '' : 'metadata'
  if (target?.word) nextTick(() => editor.value?.surface?.focus())
}

function focusFormulaField(key, offset) {
  nextTick(() => {
    const input = key === 'answer' ? answerInput.value : explanationInput.value
    input?.focus()
    input?.setSelectionRange(offset, offset)
  })
}

function applyFormula(latex) {
  const target = formula.value
  run(async () => {
    const { omml } = await api('/exams/equation', { method: 'POST', body: { latex } })
    if (target.word) {
      insertWordFormula(target, omml)
    } else {
      const value = meta.value[target.key]
      const wrapped = latex.includes('\n') ? '\\[' + latex + '\\]' : '\\(' + latex + '\\)'
      const updated = value.slice(0, target.start) + wrapped + value.slice(target.end)
      if (updated.length > (target.key === 'answer' ? 3000 : 4000)) throw new Error('超过该字段的字数上限')
      meta.value[target.key] = updated
      closeFormula()
      focusFormulaField(target.key, target.start + wrapped.length)
      return
    }
    closeFormula()
  }, formError)
}

function insertWordFormula(target, omml) {
  const instance = editor.value
  const surface = instance.surface
  const { anchor, head } = target.selection
  if (anchor.paragraphId !== head.paragraphId) throw new Error('请将光标放在同一段落内插入公式')
  surface.setSelection(target.selection)
  const name = 'dm_' + crypto.randomUUID().replaceAll('-', '')
  const host = createBrowserAutomationHost(instance)
  const execute = (operation) => {
    const result = host.execute({ operations: [operation] })
    if (!result.ok) {
      const failure = result.results.find((item) => item.status === 'error')
      throw new Error(failure?.error?.message || 'Word 无法在当前位置写入公式，请将光标移到普通正文后重试')
    }
    return result.results[0].value
  }
  let marked = false
  try {
    marked = instance.exec({ type: 'insertBookmark', name }).ok
    if (!marked) throw new Error('当前位置不可插入公式')
    const { handle } = execute({ op: 'getDocument' })
    const { handle: body } = execute({ op: 'getBody', document: handle })
    const { handles } = execute({ op: 'getBookmarks', scope: { body } })
    const bookmark = handles.find((item) => execute({ op: 'getBookmarkName', bookmark: item }).text === name)
    const span = bookmark && execute({ op: 'getBookmarkRange', bookmark }).span
    if (!span) throw new Error('无法定位公式插入点，请在普通正文中重新定位光标')
    execute({ op: 'insertOoxml', span, location: 'Replace', ooxml: equationPackage(omml) })
    changed()
  } finally {
    if (marked) instance.exec({ type: 'deleteBookmark', name })
    host.dispose()
  }
}

function changed() {
  changes += 1
  dirty.value = true
}

function documentChanged(change) {
  if (change.source !== 'load') changed()
  updatePage()
}

async function persist() {
  if (!dirty.value) return true
  const instance = editor.value
  const version = changes
  const content = await instance?.save()
  if (!content) throw new Error('无法保存 Word 正文')
  const body = new FormData()
  body.append('file', new Blob([content], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' }), 'exam.docx')
  body.append('title', exam.value.title.trim())
  body.append('revision', exam.value.revision)
  if (editing.value === 'sheet') {
    sheetState.value = await api(`${path}/sheet/document`, { method: 'PUT', body })
    exam.value.revision = sheetState.value.revision
  } else if (editing.value === 'answers') {
    answerState.value = await api(`${path}/answers/document`, { method: 'PUT', body })
    exam.value.revision = answerState.value.revision
  } else exam.value = await api(`${path}/document`, { method: 'PUT', body })
  dirty.value = version !== changes
  return !dirty.value
}

async function run(operation, targetError = error) {
  if (busy.value) return
  busy.value = true
  targetError.value = ''
  try { await operation() }
  catch (failure) { targetError.value = failure.message }
  finally { busy.value = false }
}

function locate(question) {
  selected.value = question.id
  if (!editor.value?.exec({ type: 'goToBookmark', name: question.id }).ok) {
    error.value = '题目定位已失效，请重新选中正文标记。'
  }
}

function markSelection() {
  if (!selectionText.value.trim()) return
  run(async () => {
    if (editor.value.query({ type: 'bookmarks' })?.some((entry) => entry.atSelection && entry.name.startsWith('dexam_'))) {
      throw new Error('选区已有题目标记，请先移除原标记，再重新选择范围')
    }
    const name = `dexam_${crypto.randomUUID().replaceAll('-', '')}`
    const result = editor.value.exec({ type: 'insertBookmark', name })
    if (!result.ok) throw new Error('无法标记此选区，请选择一道题的完整段落')
    changed()
    if (!await persist()) return
    selected.value = name
    if (active.value) {
      openMetadata(active.value)
    } else {
      editor.value.exec({ type: 'deleteBookmark', name })
      changed()
      await persist()
      selected.value = ''
      throw new Error('请选择一道题的连续段落，表格内请在同一单元格选择')
    }
  })
}

function removeMarker() {
  run(async () => {
    if (!editor.value.exec({ type: 'deleteBookmark', name: selected.value }).ok) throw new Error('无法移除题目标记')
    changed()
    if (await persist()) selected.value = ''
  })
}

function openMetadata(question) {
  selected.value = question.id
  formError.value = ''
  meta.value = { kind: question.kind, points: question.points, answer: question.answer,
    explanation: question.explanation, tags: question.tags.join('、') }
  modal.value = 'metadata'
}

function saveMetadata() {
  const key = selected.value
  run(async () => {
    if (!await persist()) return
    const fields = meta.value
    exam.value = await api(`${path}/questions/${key}`, { method: 'PUT', body: {
      ...fields, revision: exam.value.revision, points: fields.points || null,
      tags: fields.tags.split(/[、,，]/).map((tag) => tag.trim()).filter(Boolean),
    } })
    modal.value = ''
  }, formError)
}

function openRevision() {
  if (!active.value?.confirmed) return
  formError.value = ''
  instruction.value = ''
  mode.value = 'replace'
  candidate.value = null
  modal.value = 'revision'
}

function editorShortcut(event) {
  if (!event.isComposing && event.altKey && !event.ctrlKey && event.code === 'Equal' && ready.value) {
    event.preventDefault()
    openWordFormula()
    return
  }
  if (editing.value !== 'paper') return
  if (event.isComposing || !event.altKey || event.ctrlKey || event.code !== 'Backslash' || busy.value) return
  event.preventDefault()
  updateSelection(true)
  if (active.value?.confirmed && active.value.replaceable) openRevision()
  else error.value = '请先定位并确认一道题，再使用 AI 修改'
}

function revise() {
  const key = selected.value
  candidate.value = null
  run(async () => {
    if (!await persist()) return
    const editVersion = changes
    const proposal = await api(`${path}/questions/${key}/revise`, {
      method: 'POST', body: { revision: exam.value.revision, mode: mode.value, instruction: instruction.value },
    })
    if (changes !== editVersion) throw new Error('正文在生成期间已修改，请重新生成候选')
    candidate.value = proposal
  }, formError)
}

function adopt() {
  const key = selected.value
  run(async () => {
    if (dirty.value || exam.value.revision !== candidate.value.revision) throw new Error('正文已变化，请重新生成候选')
    const row = await api(`${path}/questions/${key}/adopt`, {
      method: 'POST', body: { revision: candidate.value.revision, question: candidate.value.question },
    })
    await load(row)
    modal.value = ''
    candidate.value = null
  }, formError)
}

function showPreview(variant) {
  if (preview.value === variant) { preview.value = ''; return }
  run(async () => {
    if (!await persist()) return
    page.value = 1
    preview.value = variant
  })
}

function editVariant(variant, regenerate = false) {
  run(async () => {
    if (regenerate && !window.confirm('按当前题目重新生成参考答案？保存后将替换原有的答案文档。')) return
    if (!regenerate && !await persist()) return
    const editVersion = changes
    const state = variant === 'paper' ? null : await api(`${path}/${variant}`)
    const document = variant === 'sheet' && !state.saved ? null : await getDocument(variant, regenerate)
    if (editVersion !== changes) throw new Error('当前文档有新的修改，请保存后再切换')
    activateDocument(variant, document)
    if (variant === 'answers') answerState.value = state
    if (variant === 'sheet') sheetState.value = state
    dirty.value = regenerate
  })
}

async function getDocument(variant, regenerate = false) {
  const endpoint = variant === 'paper' ? path : `${path}/${variant}`
  const file = await api(`${endpoint}/document?revision=${exam.value.revision}${regenerate ? '&regenerate=true' : ''}`,
    { binary: true })
  return file.arrayBuffer()
}

function activateDocument(variant, document) {
  selectionUnsubscribe?.()
  equationUnsubscribe?.()
  selectionUnsubscribe = null
  equationUnsubscribe = null
  equationSources.clear()
  editor.value = null
  bytes.value = document
  editing.value = variant
  preview.value = ''
  documentKey.value += 1
}

function showSheetLayout() {
  run(async () => {
    if (!await persist()) return
    sheetState.value = await api(`${path}/sheet`)
    formError.value = ''
    modal.value = 'sheet'
  })
}

function buildSheet(layout) {
  run(async () => {
    if (!await persist()) return
    sheetState.value = await api(`${path}/sheet`, { method: 'PUT', body: { ...layout, revision: exam.value.revision } })
    exam.value.revision = sheetState.value.revision
    activateDocument('sheet', await getDocument('sheet'))
    modal.value = ''
  }, formError)
}

function showSources() {
  run(async () => {
    const files = await api(`/resources?course_id=${exam.value.course_id}`)
    resources.value = files.filter((file) => file.status === 'ready' && file.page_count
      && (!['doc', 'docx'].includes(file.extension) || file.has_preview))
    sourceDraft.value = exam.value.sources.map((source) => ({ ...source }))
    formError.value = ''
    modal.value = 'sources'
  })
}

function saveSources() {
  run(async () => {
    if (!await persist()) return
    exam.value = await api(`${path}/sources`, { method: 'PUT', body: {
      revision: exam.value.revision, sources: sourceDraft.value,
    } })
    modal.value = ''
  }, formError)
}

function review() {
  run(async () => {
    if (!await persist()) return
    exam.value = await api(`${path}/review`, { method: 'PUT', body: { revision: exam.value.revision, reviewed: true } })
    modal.value = pendingExport ? 'export' : ''
    pendingExport = false
  }, formError)
}

function exportFile(variant, format) {
  run(async () => {
    if (variant === 'paper' && (!exam.value.reviewed || (editing.value === 'paper' && dirty.value))) {
      formError.value = ''
      pendingExport = true
      modal.value = 'review'
      return
    }
    if (await persist()) await download(`${path}/export/${variant}/${format}`, `${exam.value.title}.${format === 'latex-pdf' ? 'pdf' : format}`)
  }, formError)
}
</script>

<template>
  <div class="page exam-page">
    <RouterLink class="text-link back-link" to="/exams"><ArrowLeft :size="16" /> 返回试卷管理</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state" role="status">正在加载试卷</p>
    <template v-if="exam">
      <header class="page-heading">
        <div class="editor-title">
          <input v-model="exam.title" aria-label="试卷名称" maxlength="160" :disabled="busy || !!preview || editing !== 'paper'" @input="changed">
          <p role="status">v{{ exam.revision }} · {{ dirty ? '有未保存的修改' : '已保存' }} · 已标记 {{ exam.questions.length }} 题 / {{ exam.total_points }} 分</p>
        </div>
        <div class="actions">
          <button class="button secondary" :disabled="busy" @click="showSources">参考资料</button>
          <button class="button secondary" :disabled="busy || !canPreview" @click="showPreview(editing)"><Eye :size="17" /> {{ preview ? '返回编辑' : 'PDF 预览' }}</button>
          <button class="button secondary" :disabled="busy || !canPreview" @click="formError = ''; modal = 'export'"><Download :size="17" /> 导出</button>
          <button class="button primary" :disabled="!ready || !dirty" @click="run(persist)"><Save :size="17" /> 保存</button>
        </div>
      </header>
      <div class="segmented exam-edit-tabs" aria-label="编辑文档">
        <button :aria-pressed="editing === 'paper'" :disabled="busy" @click="editing !== 'paper' && editVariant('paper')">编辑试卷</button>
        <button :aria-pressed="editing === 'answers'" :disabled="busy" @click="editing !== 'answers' && editVariant('answers')">编辑参考答案</button>
        <button :aria-pressed="editing === 'sheet'" :disabled="busy" @click="editing !== 'sheet' && editVariant('sheet')">编辑答题卡</button>
      </div>
      <div v-if="editing === 'sheet'" class="exam-review">
        <span>{{ sheetState?.stale ? '试卷题目或卷头已更新，请核对答题卡。' : sheetState?.saved ? '可调整各题作答区，或在 Word 中直接编辑。' : '从试卷已确认的题目生成答题卡。' }}</span>
        <button class="button secondary" :disabled="busy" @click="showSheetLayout">{{ sheetState?.saved ? '设置作答区' : '生成答题卡' }}</button>
      </div>
      <div v-if="editing === 'answers' && answerState?.stale" class="exam-review">
        <span>这份答案保存后试卷版本已有更新，请核对题目与答案。</span>
        <button class="button secondary" :disabled="busy" @click="editVariant('answers', true)">按当前题目重新生成</button>
      </div>
      <div v-if="editing === 'paper' && (!exam.reviewed || dirty)" class="exam-review">
        <span>{{ exam.answer_markers ? '正文检测到答案或评分说明，请移出后再确认。' : '下载学生卷前，请检查正文是否含参考答案。' }}</span>
        <button class="button secondary" :disabled="busy" @click="pendingExport = false; formError = ''; modal = 'review'">确认学生卷</button>
      </div>
      <PdfViewer v-if="preview" :key="preview" :src="`/api${path}/export/${preview}/pdf?inline=true&v=${exam.revision}`" v-model:page="page" />
      <div v-if="bytes" v-show="!preview" :class="{ 'exam-workspace': editing === 'paper' }">
        <aside v-if="editing === 'paper'" class="panel exam-index" aria-label="题目列表">
          <header class="stack">
            <h2>题目</h2>
            <button class="button secondary" :disabled="!ready || !selectionText.trim()" @mousedown.prevent @click="markSelection"><BookmarkPlus :size="17" /> 将选区标为一题</button>
          </header>
          <p v-if="!exam.questions.length" class="muted">请在正文选中一道题的完整段落后标记。</p>
          <div class="exam-question-list">
            <button v-for="(question, index) in exam.questions" :key="question.id" type="button" :disabled="!ready"
              :aria-pressed="question.id === selected" class="exam-question" @mousedown.prevent @click="locate(question)">
              <span>{{ index + 1 }} · {{ examKinds[question.kind] }}<template v-if="question.points"> · {{ question.points }} 分</template></span>
              <strong><MathPreview :source="question.text.split('\n')[0]" /></strong>
              <small v-if="!question.confirmed">{{ question.placeholder ? '空题位 · 待确认' : '待确认' }}</small>
            </button>
          </div>
          <div v-if="active" class="stack exam-question-actions">
            <button class="button secondary" :disabled="!ready" @click="openMetadata(active)">{{ active.confirmed ? '题目信息与答案' : '确认题型与答案' }}</button>
            <button class="button primary" :disabled="!ready || !active.confirmed || !active.replaceable" @click="openRevision"><Sparkles :size="16" /> AI 修改本题</button>
            <p v-if="!active.replaceable" class="muted">请在 Word 中手动编辑这道题的复杂内容或重新标记完整段落。</p>
            <button class="button subtle" :disabled="!ready" @click="removeMarker">移除题目标记</button>
          </div>
        </aside>
        <section class="word-editor" :aria-label="`Word ${documentLabels[editing]}编辑器`" @keydown.capture="editorShortcut($event)">
          <LocaleProvider :i18n="zhCN">
            <DocxEditorRoot :key="documentKey" :document="bytes" locale="zh-CN" :color-mode="theme" :fonts="fonts" @ready="editorReady" @change="documentChanged">
              <div class="word-toolbar"><DocxEditorToolbar>
                <DocxEditorToolbar.Group id="insert" label="插入" after="text" :priority="75">
                  <DocxEditorToolbar.ImageInsert /><DocxEditorToolbar.TableInsert />
                  <button type="button" class="exam-formula-tool" title="插入公式" aria-label="插入公式"
                    :disabled="!ready" @mousedown.prevent @click="openWordFormula()"><Sigma :size="16" /> 公式</button>
                </DocxEditorToolbar.Group>
              </DocxEditorToolbar></div>
              <DocxEditorUnsupportedElement :match="isEquation">
                <template #default="{ element }">
                  <button v-equation-box type="button" class="word-math-vector" aria-label="编辑此公式" @pointerdown.prevent
                    @click.stop="openPreviewEquation(element, $event)"><MathPreview :source="rememberEquation(element)" /></button>
                </template>
              </DocxEditorUnsupportedElement>
              <div class="word-actions">
                <form v-if="wordPages" class="word-page-number" @submit.prevent="jumpPage">
                  <label>页 <input name="page" :value="wordPage" aria-label="跳转到试卷页码" type="number" min="1" :max="wordPages"></label>
                  <span>/ {{ wordPages }}</span>
                </form>
              </div>
              <div class="word-canvas" @scroll.capture="updatePage" @click.capture="onEquationClick">
                <DocxEditorViewport class="word-viewport">
                  <DocxEditorContent /><DocxEditorHyperLink /><DocxEditorContextMenu /><DocxEditorContentControl />
                </DocxEditorViewport>
                <DocxEditorLoading overlay />
              </div>
              <DocxEditorOpenFailure />
            </DocxEditorRoot>
          </LocaleProvider>
        </section>
      </div>
    </template>
    <Modal :open="modal === 'sheet'" title="设置答题卡作答区" wide @close="!busy && (modal = '')">
      <AnswerSheetLayout v-if="sheetState" :state="sheetState" :disabled="busy" @build="buildSheet" />
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      <div v-if="sheetState?.can_build" class="dialog-actions">
        <button class="button primary" type="submit" form="answer-sheet-layout" :disabled="busy">{{ busy ? '正在生成…' : '生成答题卡' }}</button>
      </div>
    </Modal>
    <Modal :open="modal === 'export'" :title="`导出${documentLabels[editing]}`" @close="!busy && (modal = '')">
      <div class="stack">
        <div class="exam-export-options stack">
          <div class="actions">
            <button v-for="format in ['docx', 'doc', 'pdf']" :key="format" class="button secondary" :disabled="busy" @click="exportFile(editing, format)">{{ formats[format] }}</button>
          </div>
        </div>
        <div class="exam-export-options stack">
          <p class="muted">LaTeX 按已确认的题目、参考答案字段和作答区设置重新排版。Word 中的手动排版、图片和表格请通过 Word 或 PDF 导出。</p>
          <div class="actions">
            <button v-for="format in ['tex', 'latex-pdf']" :key="format" class="button secondary" :disabled="busy" @click="exportFile(editing, format)">{{ formats[format] }}</button>
          </div>
        </div>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      </div>
    </Modal>
    <Modal :open="modal === 'formula'" :title="formula?.replace ? '编辑公式' : '插入数学公式'" wide @close="!busy && closeFormula()">
      <FormulaEditor v-if="formula" :initial="formula.source" :replace="formula.replace" :busy="busy" @apply="applyFormula" />
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
    </Modal>
    <Modal :open="modal === 'metadata'" title="题目信息与教师答案" wide @close="!busy && (modal = '')">
      <form v-if="meta" class="stack" @submit.prevent="saveMetadata">
        <label>题型<select v-model="meta.kind"><option v-for="(label, key) in examKinds" :key="key" :value="key">{{ label }}</option></select></label>
        <label>分值<input v-model.number="meta.points" type="number" min="1" max="100"></label>
        <label>标签<input v-model="meta.tags" maxlength="240" placeholder="例如：编程、函数"></label>
        <label>参考答案<textarea ref="answerInput" v-model="meta.answer" rows="3" maxlength="3000"></textarea></label>
        <button type="button" class="button secondary formula-keyboard-toggle" @mousedown.prevent @click="openTextFormula('answer')"><Sigma :size="15" /> 编辑答案公式</button>
        <div v-if="meta.answer" class="formula-preview" aria-label="参考答案预览"><MathPreview :source="meta.answer" /></div>
        <label>解析与评分要点<textarea ref="explanationInput" v-model="meta.explanation" rows="4" maxlength="4000"></textarea></label>
        <button type="button" class="button secondary formula-keyboard-toggle" @mousedown.prevent @click="openTextFormula('explanation')"><Sigma :size="15" /> 编辑评分公式</button>
        <div v-if="meta.explanation" class="formula-preview" aria-label="评分要点预览"><MathPreview :source="meta.explanation" /></div>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions"><button type="submit" class="button primary" :disabled="busy">保存并确认题目</button></div>
      </form>
    </Modal>
    <Modal :open="modal === 'revision'" title="AI 修改本题" wide @close="!busy && (modal = '')">
      <form class="stack" @submit.prevent="revise">
        <label>修改方式<select v-model="mode" :disabled="busy" @change="candidate = null">
          <option v-for="(label, key) in revisionModes" :key="key" :value="key" :disabled="key === 'options' && !['single', 'multiple'].includes(active?.kind)">{{ label }}</option>
        </select></label>
        <label>修改要求<textarea v-model="instruction" rows="3" maxlength="2000" :disabled="busy" @input="candidate = null"></textarea></label>
        <div v-if="candidate" class="exam-comparison">
          <div><h3>原题</h3><MathPreview :source="active?.text" /><p>参考答案 · <MathPreview :source="active?.answer || '未填写'" /></p></div>
          <div><h3>候选 · {{ candidate.question.points }} 分</h3><MathPreview :source="candidate.question.stem" />
            <ol v-if="candidate.question.options.length" type="A"><li v-for="(option, i) in candidate.question.options" :key="i"><MathPreview :source="option" /></li></ol>
            <p>参考答案 · <MathPreview :source="candidate.question.answer" /></p><MathPreview v-if="candidate.question.explanation" :source="candidate.question.explanation" />
          </div>
        </div>
        <p v-for="reference in candidate?.references" :key="reference.title" class="muted">{{ reference.title }} · 第 {{ reference.pages.join('、') }} 页</p>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions">
          <button type="submit" class="button" :class="candidate ? 'secondary' : 'primary'" :disabled="busy">{{ busy ? '正在处理…' : candidate ? '重新生成' : '生成候选' }}</button>
          <button v-if="candidate" type="button" class="button primary" :disabled="busy" @click="adopt">采纳并替换本题</button>
        </div>
      </form>
    </Modal>
    <Modal :open="modal === 'review'" title="确认学生卷" @close="!busy && (modal = '')">
      <p>确认已核对试卷正文，并将参考答案及评分说明移至教师答案。</p>
      <p v-if="formError" class="error" role="alert">{{ formError }}</p>
      <div class="dialog-actions"><button type="button" class="button primary" :disabled="busy" @click="review">确认可导出</button></div>
    </Modal>
    <Modal :open="modal === 'sources'" title="参考资料" wide @close="!busy && (modal = '')">
      <form class="stack" @submit.prevent="saveSources">
        <MapSources v-model="sourceDraft" :resources="resources" />
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions"><button type="submit" class="button primary" :disabled="busy">保存参考资料</button></div>
      </form>
    </Modal>
  </div>
</template>
