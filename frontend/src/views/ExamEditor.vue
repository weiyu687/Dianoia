<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  DocxEditorContent, DocxEditorContentControl, DocxEditorContextMenu, DocxEditorEquation, DocxEditorHyperLink,
  DocxEditorLoading, DocxEditorOpenFailure, DocxEditorRoot, DocxEditorToolbar, DocxEditorViewport, LocaleProvider,
} from '@docx-editor.dev/vue'
import { zhCN } from '@docx-editor.dev/i18n'
import { setHarfBuzzWasmUrl } from '@docx-editor.dev/core/layout'
import harfBuzzWasm from '@docx-editor.dev/core/harfbuzz.wasm?url'
import '@docx-editor.dev/vue/styles.css'
import { ArrowLeft, BookmarkPlus, Download, Eye, Save, Sparkles } from 'lucide-vue-next'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { api, download } from '../api'
import Modal from '../components/Modal.vue'
import MapSources from '../components/MapSources.vue'
import PdfViewer from '../components/PdfViewer.vue'
import { examKinds } from '../examKinds'
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
const instruction = ref('')
const mode = ref('replace')
const candidate = ref(null)
const preview = ref('')
const sourceDraft = ref([])
const resources = ref([])
const page = ref(1)
const wordPage = ref(1)
const wordPages = ref(0)
const ready = computed(() => !!editor.value && !busy.value)
const active = computed(() => exam.value?.questions.find((question) => question.id === selected.value))
const fonts = { supportedFamilies: ['宋体', '黑体', '仿宋', '楷体', '微软雅黑', '等线', '华文中宋', '思源宋体'] }
const revisionModes = { replace: '重新出题', stem: '修改题干', options: '修改干扰项', difficulty: '调整难度' }
let selectionUnsubscribe
let changes = 0

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
  window.removeEventListener('beforeunload', beforeUnload)
})

function beforeUnload(event) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => !dirty.value || window.confirm('当前有未保存的试卷修改，确定离开？'))

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
  updateSelection()
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
  exam.value = await api(`${path}/document`, { method: 'PUT', body })
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
    modal.value = ''
  }, formError)
}

function exportFile(variant, format) {
  run(async () => {
    if (variant === 'paper' && (!exam.value.reviewed || dirty.value)) {
      formError.value = ''
      modal.value = 'review'
      return
    }
    if (await persist()) await download(`${path}/export/${variant}/${format}`, `${exam.value.title}.${format}`)
  })
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
          <input v-model="exam.title" aria-label="试卷名称" maxlength="160" :disabled="busy || !!preview" @input="changed">
          <p role="status">v{{ exam.revision }} · {{ dirty ? '有未保存的修改' : '已保存' }} · 已标记 {{ exam.questions.length }} 题 / {{ exam.total_points }} 分</p>
        </div>
        <div class="actions">
          <button class="button secondary" :disabled="busy" @click="showSources">参考资料</button>
          <button class="button secondary" :disabled="busy" @click="showPreview('paper')"><Eye :size="17" /> {{ preview === 'paper' ? '返回编辑' : '学生卷预览' }}</button>
          <button class="button secondary" :disabled="busy" @click="showPreview('answers')"><Eye :size="17" /> {{ preview === 'answers' ? '返回编辑' : '答案预览' }}</button>
          <details class="row-menu export-menu"><summary class="button secondary"><Download :size="17" /> 导出</summary><div>
            <button v-for="format in ['docx', 'doc']" :key="`paper-${format}`" :disabled="busy" @click="exportFile('paper', format)">学生卷 (.{{ format }})</button>
            <button v-for="format in ['docx', 'doc']" :key="`answers-${format}`" :disabled="busy" @click="exportFile('answers', format)">教师答案 (.{{ format }})</button>
          </div></details>
          <button class="button primary" :disabled="!ready || !dirty" @click="run(persist)"><Save :size="17" /> 保存</button>
        </div>
      </header>
      <div v-if="!exam.reviewed || dirty" class="exam-review">
        <span>{{ exam.answer_markers ? '正文检测到答案或评分说明，请移出后再确认。' : '下载学生卷前，请检查正文是否含参考答案。' }}</span>
        <button class="button secondary" :disabled="busy" @click="formError = ''; modal = 'review'">确认学生卷</button>
      </div>
      <PdfViewer v-if="preview" :key="preview" :src="`/api${path}/export/${preview}/pdf?inline=true&v=${exam.revision}`" v-model:page="page" />
      <div v-show="!preview" class="exam-workspace">
        <aside class="panel exam-index" aria-label="题目列表">
          <header class="stack">
            <h2>题目</h2>
            <button class="button secondary" :disabled="!ready || !selectionText.trim()" @mousedown.prevent @click="markSelection"><BookmarkPlus :size="17" /> 将选区标为一题</button>
          </header>
          <p v-if="!exam.questions.length" class="muted">请在正文选中一道题的完整段落后标记。</p>
          <div class="exam-question-list">
            <button v-for="(question, index) in exam.questions" :key="question.id" type="button" :disabled="!ready"
              :aria-pressed="question.id === selected" class="exam-question" @mousedown.prevent @click="locate(question)">
              <span>{{ index + 1 }} · {{ examKinds[question.kind] }}<template v-if="question.points"> · {{ question.points }} 分</template></span>
              <strong>{{ question.text.split('\n')[0] }}</strong>
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
        <section class="word-editor" aria-label="Word 试卷编辑器" @keydown.capture="editorShortcut">
          <LocaleProvider :i18n="zhCN">
            <DocxEditorRoot :document="bytes" locale="zh-CN" :color-mode="theme" :fonts="fonts" @ready="editorReady" @change="documentChanged">
              <div class="word-toolbar"><DocxEditorToolbar>
                <DocxEditorToolbar.Group id="insert" label="插入" after="text" :priority="75">
                  <DocxEditorToolbar.ImageInsert /><DocxEditorToolbar.TableInsert />
                </DocxEditorToolbar.Group>
              </DocxEditorToolbar></div>
              <div class="word-actions">
                <form v-if="wordPages" class="word-page-number" @submit.prevent="jumpPage">
                  <label>页 <input name="page" :value="wordPage" aria-label="跳转到试卷页码" type="number" min="1" :max="wordPages"></label>
                  <span>/ {{ wordPages }}</span>
                </form>
              </div>
              <div class="word-canvas" @scroll.capture="updatePage">
                <DocxEditorViewport class="word-viewport">
                  <DocxEditorContent /><DocxEditorHyperLink /><DocxEditorContextMenu /><DocxEditorEquation /><DocxEditorContentControl />
                </DocxEditorViewport>
                <DocxEditorLoading overlay />
              </div>
              <DocxEditorOpenFailure />
            </DocxEditorRoot>
          </LocaleProvider>
        </section>
      </div>
    </template>
    <Modal :open="modal === 'metadata'" title="题目信息与教师答案" @close="!busy && (modal = '')">
      <form v-if="meta" class="stack" @submit.prevent="saveMetadata">
        <label>题型<select v-model="meta.kind"><option v-for="(label, key) in examKinds" :key="key" :value="key">{{ label }}</option></select></label>
        <label>分值<input v-model.number="meta.points" type="number" min="1" max="100"></label>
        <label>标签<input v-model="meta.tags" maxlength="240" placeholder="例如：编程、函数"></label>
        <label>参考答案<textarea v-model="meta.answer" rows="3" maxlength="3000"></textarea></label>
        <label>解析与评分要点<textarea v-model="meta.explanation" rows="4" maxlength="4000"></textarea></label>
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
          <div><h3>原题</h3><pre>{{ active?.text }}</pre><p>参考答案 · {{ active?.answer || '未填写' }}</p></div>
          <div><h3>候选 · {{ candidate.question.points }} 分</h3><pre>{{ candidate.question.stem }}</pre>
            <ol v-if="candidate.question.options.length" type="A"><li v-for="(option, i) in candidate.question.options" :key="i">{{ option }}</li></ol>
            <p>参考答案 · {{ candidate.question.answer }}</p><pre v-if="candidate.question.explanation">{{ candidate.question.explanation }}</pre>
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
