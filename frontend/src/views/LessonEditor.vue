<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import {
  DocxEditorContent, DocxEditorContentControl, DocxEditorContextMenu, DocxEditorEquation,
  DocxEditorHyperLink, DocxEditorLoading, DocxEditorOpenFailure, DocxEditorRoot,
  DocxEditorToolbar, DocxEditorViewport, LocaleProvider,
} from '@docx-editor.dev/vue'
import { zhCN } from '@docx-editor.dev/i18n'
import '@docx-editor.dev/vue/styles.css'
import { ArrowLeft, Download, Eye, Save, Sparkles } from 'lucide-vue-next'
import { onBeforeRouteLeave, useRoute } from 'vue-router'
import { api, download } from '../api'
import PdfViewer from '../components/PdfViewer.vue'
import { theme } from '../session'

const id = String(useRoute().params.id)
const lesson = ref(null)
const documentBytes = shallowRef(null)
const editor = shallowRef(null)
const editable = ref(false)
const loading = ref(true)
const changed = ref(false)
const saving = ref(false)
const notice = ref('')
const error = ref('')
const preview = ref(false)
const previewPage = ref(1)
const page = ref(1)
const totalPages = ref(0)
const pageInput = ref(null)
const mode = ref('')
const instruction = ref('')
const instructionInput = ref(null)
const writing = ref(false)
const suggestion = ref('')
let editVersion = 0
let writingVersion = 0
let writingDocumentRevision = null
let selectionPin = null
let unsubscribe = null

onMounted(async () => {
  window.addEventListener('beforeunload', preventUnload)
  try {
    const info = await api(`/lessons/${id}`)
    const response = await api(`/lessons/${id}/document?revision=${info.revision}`, { binary: true })
    documentBytes.value = await response.arrayBuffer()
    lesson.value = info
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function editorReady(instance) {
  editor.value = instance
  editable.value = instance.snapshot().editable
  unsubscribe?.()
  unsubscribe = instance.on('selectionChange', updatePage)
  updatePage()
}

function updatePage() {
  const instance = editor.value
  if (!instance) return
  page.value = instance.getCurrentPage('viewport') || 1
  totalPages.value = instance.getTotalPages()
}

function jumpPage() {
  const input = pageInput.value
  const destination = Number(input.value)
  if (Number.isInteger(destination) && destination >= 1 && destination <= totalPages.value) {
    editor.value?.scrollToPage(destination)
  }
  updatePage()
  input.value = page.value
}

function preventUnload(event) {
  if (!changed.value) return
  event.preventDefault()
  event.returnValue = ''
}
onBeforeRouteLeave(() => !changed.value || window.confirm('当前有未保存的教案修改，确定离开？'))
onBeforeUnmount(() => {
  clearWriting()
  unsubscribe?.()
  window.removeEventListener('beforeunload', preventUnload)
})

function markChanged() {
  editVersion += 1
  changed.value = true
  notice.value = ''
}
function documentChanged(change) {
  if (change.source === 'load') return
  markChanged()
  updatePage()
  if (writingDocumentRevision !== null && change.revision > writingDocumentRevision) clearWriting()
}

async function save() {
  if (!changed.value || saving.value) return !changed.value
  const title = lesson.value.title.trim()
  if (!title) {
    error.value = '教案名称不能为空'
    return false
  }
  saving.value = true
  error.value = ''
  const version = editVersion
  try {
    const content = await editor.value.save()
    if (!content) throw new Error('无法保存 Word 正文，请重新打开教案')
    const body = new FormData()
    body.append('file', new Blob([content], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }), 'lesson.docx')
    body.append('title', title)
    body.append('revision', lesson.value.revision)
    const saved = await api(`/lessons/${id}/document`, { method: 'PUT', body })
    lesson.value.revision = saved.revision
    changed.value = version !== editVersion
    if (!changed.value) lesson.value.title = saved.title
    return !changed.value
  } catch (failure) {
    error.value = failure.message
    return false
  } finally { saving.value = false }
}

async function showPreview() {
  if (preview.value) { preview.value = false; return }
  if (await save()) {
    clearWriting()
    previewPage.value = 1
    preview.value = true
  }
}

async function exportFile(format, event) {
  event.target.closest('details').open = false
  try {
    if (await save()) await download(`/lessons/${id}/export/${format}`, `${lesson.value.title}.${format}`)
  } catch (failure) { error.value = failure.message }
}

function clearWriting(restoreFocus = false) {
  writingVersion += 1
  writing.value = false
  suggestion.value = ''
  mode.value = ''
  writingDocumentRevision = null
  if (restoreFocus) editor.value?.focus()
  if (selectionPin) editor.value?.releaseSelection(selectionPin)
  selectionPin = null
}

async function openWriting(type) {
  clearWriting()
  notice.value = ''
  error.value = ''
  const snapshot = editor.value?.snapshot()
  if (!snapshot?.editable || !snapshot.selection) {
    notice.value = '请先在正文中定位光标或选择文字'
    return
  }
  if (type === 'continue' && !snapshot.selectionCollapsed) {
    notice.value = '请把光标放到要续写的位置'
    return
  }
  if (type === 'rewrite' && snapshot.selectionCollapsed) {
    notice.value = '请先选中要重写的文字'
    return
  }
  selectionPin = editor.value.retainSelection()
  mode.value = type
  instruction.value = ''
  await nextTick()
  instructionInput.value?.focus()
}

function writingContext(instance, type) {
  if (type === 'rewrite') return { before: instance.query({ type: 'selectedText' }), after: '' }
  const { to } = instance.snapshot().selection
  const paragraphs = instance.query({ type: 'paragraphs', container: to.container })
  const position = paragraphs.findIndex((item) => item.paraId && item.paraId === to.paraId)
  if (position < 0) {
    return { before: paragraphs.slice(0, 24).map((item) => item.text).join('\n').slice(0, 14000), after: '' }
  }
  const context = (items) => items.map((item) => item.text).join('\n')
  return {
    before: context(paragraphs.slice(Math.max(0, position - 18), position + 1)).slice(-14000),
    after: context(paragraphs.slice(position + 1, position + 8)).slice(0, 14000),
  }
}

async function requestWriting() {
  if (writing.value || !mode.value) return
  const type = mode.value
  const version = ++writingVersion
  const selection = writingContext(editor.value, type)
  if (type === 'rewrite' && (!selection.before.trim() || selection.before.length > 14000)) {
    error.value = '请选择 1 至 14000 字的正文'
    return
  }
  writingDocumentRevision = editor.value.getDocumentHandle().revision
  writing.value = true
  suggestion.value = ''
  error.value = ''
  try {
    const result = await api('/ai/writing', { method: 'POST', body: {
      lesson_id: id, section: lesson.value.title, mode: type, instruction: instruction.value, ...selection,
    } })
    if (version !== writingVersion) return
    suggestion.value = result.text
    editor.value.focus()
  } catch (failure) {
    if (version === writingVersion) error.value = failure.message
  } finally {
    if (version === writingVersion) writing.value = false
  }
}

function applySuggestion() {
  if (!suggestion.value) return
  if (editor.value.getDocumentHandle().revision !== writingDocumentRevision) {
    clearWriting()
    notice.value = '正文已变化，请重新生成'
    return
  }
  const text = suggestion.value
  const type = mode.value
  editor.value.focus()
  const result = editor.value.exec({ type: 'pasteWithoutFormatting', text })
  clearWriting()
  if (!result.ok) {
    error.value = '无法在当前位置写入，请选择可编辑的正文'
    return
  }
  notice.value = type === 'rewrite' ? '已应用重写' : '已采纳续写'
}

function handleWritingKey(event) {
  if (event.isComposing || event.keyCode === 229) return
  const inDocument = event.target.closest('.word-canvas')
  if (inDocument && event.altKey && event.code === 'Backslash' && !event.ctrlKey && !event.metaKey && !event.repeat) {
    event.preventDefault()
    event.stopPropagation()
    openWriting('continue')
  } else if (event.key === 'Escape' && mode.value) {
    event.preventDefault()
    event.stopPropagation()
    clearWriting(true)
  } else if (inDocument && event.key === 'Tab' && !event.shiftKey && suggestion.value) {
    event.preventDefault()
    event.stopPropagation()
    applySuggestion()
  } else if (inDocument && mode.value && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
    clearWriting()
  }
}
</script>

<template>
  <div class="page lesson-page">
    <RouterLink class="text-link back-link" to="/lessons"><ArrowLeft :size="16" /> 返回教案管理</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="loading" class="empty-state" role="status">正在加载教案</p>
    <template v-if="lesson">
      <header class="page-heading">
        <div class="editor-title">
          <input v-model="lesson.title" aria-label="教案名称" maxlength="160" :disabled="!editable || preview" @input="markChanged">
          <p role="status">v{{ lesson.revision }} · {{ changed ? '有未保存的修改' : '已保存' }}</p>
        </div>
        <div class="actions">
          <button class="button secondary" :disabled="saving" @click="showPreview"><Eye :size="17" /> {{ preview ? '返回编辑' : 'PDF 预览' }}</button>
          <details class="row-menu export-menu"><summary class="button secondary"><Download :size="17" /> 导出</summary>
            <div><button :disabled="saving" @click="exportFile('docx', $event)">Word (.docx)</button><button :disabled="saving" @click="exportFile('doc', $event)">旧版 Word (.doc)</button><button :disabled="saving" @click="exportFile('pdf', $event)">PDF (.pdf)</button></div>
          </details>
          <button class="button primary" :disabled="saving || !changed || !editable" @click="save"><Save :size="17" /> {{ saving ? '正在保存' : '保存' }}</button>
        </div>
      </header>
      <PdfViewer v-if="preview" :src="`/api/lessons/${id}/export/pdf?inline=true&v=${lesson.revision}`" v-model:page="previewPage" />
      <section v-show="!preview" class="word-editor" aria-label="Word 教案编辑器" @keydown.capture="handleWritingKey">
        <LocaleProvider :i18n="zhCN">
          <DocxEditorRoot :document="documentBytes" locale="zh-CN" :color-mode="theme" @ready="editorReady" @change="documentChanged">
            <div class="word-toolbar">
              <DocxEditorToolbar>
                <DocxEditorToolbar.Group id="insert" label="插入" after="text" :priority="75">
                  <DocxEditorToolbar.ImageInsert />
                </DocxEditorToolbar.Group>
              </DocxEditorToolbar>
            </div>
            <div class="word-actions">
              <div class="actions">
                <button class="button subtle" :disabled="!editable" @mousedown.prevent @click="openWriting('continue')"><Sparkles :size="16" /> AI 续写 <kbd>Alt+\</kbd></button>
                <button class="button subtle" :disabled="!editable" @mousedown.prevent @click="openWriting('rewrite')">重写选区</button>
              </div>
              <form v-if="totalPages" class="word-page-number" @submit.prevent="jumpPage">
                <label>页 <input ref="pageInput" :value="page" aria-label="跳转到教案页码" type="number" min="1" :max="totalPages" @change="jumpPage"></label>
                <span>/ {{ totalPages }}</span>
              </form>
            </div>
            <p v-if="notice" class="word-notice" role="status">{{ notice }}</p>
            <form v-if="mode" class="writing-panel stack" @submit.prevent="requestWriting">
              <label>{{ mode === 'rewrite' ? '重写要求' : '续写要求' }}<input ref="instructionInput" v-model="instruction" maxlength="2000" placeholder="可输入对本次生成的要求"></label>
              <p v-if="suggestion" class="rewrite-result" aria-live="polite">{{ suggestion }}</p>
              <div class="actions">
                <button v-if="suggestion" class="button primary" type="button" @mousedown.prevent @click="applySuggestion">采纳 <kbd>Tab</kbd></button>
                <button v-else class="button primary" type="submit" :disabled="writing">{{ writing ? '正在生成' : '生成建议' }}</button>
                <button class="button subtle" type="button" @click="clearWriting(true)">取消 <kbd>Esc</kbd></button>
              </div>
            </form>
            <div class="word-canvas" @pointerdown.capture="mode && clearWriting()" @scroll.capture="updatePage">
              <DocxEditorViewport class="word-viewport">
                <DocxEditorContent />
                <DocxEditorHyperLink />
                <DocxEditorContextMenu />
                <DocxEditorEquation />
                <DocxEditorContentControl />
              </DocxEditorViewport>
              <DocxEditorLoading overlay />
            </div>
            <DocxEditorOpenFailure />
          </DocxEditorRoot>
        </LocaleProvider>
      </section>
    </template>
  </div>
</template>
