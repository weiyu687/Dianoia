import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from './api'

export const writingOptions = {
  continue: [
    ['续写', '紧接光标续写，衔接前后的内容。'],
    ['按要求写', '按教师要求在光标处撰写新内容。'],
  ],
  rewrite: [
    ['润色', '润色选区，保留原意。'],
    ['纠错', '纠正选区的错别字、语法与标点。'],
    ['扩写', '扩写选区，补充相关解释或示例。'],
    ['缩写', '压缩选区，保留要点。'],
    ['重写', '按教师要求重写选区。'],
  ],
}

const escapeHtml = (value) => value.replace(/[&<>]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[char])
function richTable(block) {
  const row = (cells, tag) => '<tr>' + cells.map((text) =>
    '<' + tag + ' style="border:1px solid #808080">' + escapeHtml(text) + '</' + tag + '>',
  ).join('') + '</tr>'
  return '<table border="1" style="border:1px solid #808080;border-collapse:collapse"><thead>' + row(block.header, 'th') + '</thead><tbody>'
    + block.rows.map((cells) => row(cells, 'td')).join('') + '</tbody></table>'
}

export function useLessonWriting({ editor, canvas, caret, id, title, notice }) {
  const mode = ref('')
  const action = ref(null)
  const instruction = ref('')
  const instructionInput = ref(null)
  const suggestion = ref(null)
  const busy = ref(false)
  const error = ref('')
  const anchor = ref(null)
  let pin
  let request
  let revision = null
  let frame = 0
  let dragging = false
  let selectionKey = ''
  let dismissedSelection = ''
  let insertionPoint = null
  let lastRect = null

  function selectionRect(collapsed) {
    const host = canvas.value
    if (!host) return null
    const native = document.getSelection()
    if (native?.rangeCount && host.contains(native.anchorNode) && native.isCollapsed === collapsed) {
      const rect = Array.from(native.getRangeAt(0).getClientRects()).at(-1)
      if (rect?.height) return rect
    }
    // The paginated surface can paint selections without a native DOM range.
    const selector = collapsed
      ? '.docx-editor-one-surface__caret:not([data-docx-drop-caret])'
      : '.docx-selection-mark-rect, .docx-retained-selection-rect'
    return Array.from(host.querySelectorAll(selector)).filter((node) => node.getClientRects().length).at(-1)?.getBoundingClientRect() || null
  }

  function position(allowCached = false) {
    if (!mode.value || !canvas.value) return
    const measured = selectionRect(mode.value === 'continue')
    if (measured?.height) lastRect = measured
    const rect = measured?.height ? measured : allowCached === true ? lastRect : null
    const bounds = canvas.value.getBoundingClientRect()
    if (!rect || !rect.height) {
      anchor.value = null
      return
    }
    if (rect.bottom < bounds.top || rect.top > bounds.top + bounds.height) {
      anchor.value = null
      return
    }
    const width = Math.min(suggestion.value ? 440 : action.value ? 310 : 176, bounds.width - 24)
    const left = Math.min(Math.max(12, rect.left - bounds.left), bounds.width - width - 12)
    const bottomSpace = bounds.top + bounds.height - rect.bottom
    const height = suggestion.value ? 260 : action.value ? 170 : writingOptions[mode.value].length * 36 + 12
    const above = bottomSpace < height && rect.top - bounds.top > bottomSpace
    anchor.value = {
      left: left + 'px',
      width: width + 'px',
      ...(above ? { bottom: bounds.top + bounds.height - rect.top + 6 + 'px' } : { top: Math.max(0, rect.bottom - bounds.top) + 6 + 'px' }),
    }
  }

  function clear(restoreFocus = false) {
    request?.abort()
    request = null
    revision = null
    mode.value = ''
    action.value = null
    instruction.value = ''
    suggestion.value = null
    busy.value = false
    error.value = ''
    anchor.value = null
    insertionPoint = null
    lastRect = null
    dismissedSelection = selectionKey
    selectionKey = ''
    if (restoreFocus) editor.value?.focus()
    if (pin) editor.value?.releaseSelection(pin)
    pin = null
  }

  function open(nextMode, key = '') {
    clear()
    notice.value = ''
    mode.value = nextMode
    selectionKey = key
    if (nextMode === 'continue') {
      const rect = selectionRect(true)
      if (rect?.height) insertionPoint = editor.value.positionAtPoint(rect.left, rect.top + rect.height / 2)
    }
    pin = editor.value.retainSelection()
    position()
  }

  function updateSelection() {
    frame = 0
    const instance = editor.value
    if (!instance || dragging || !canvas.value?.contains(document.activeElement)) return
    const state = instance.snapshot()
    if (!state.editable || !state.selection || state.image || state.selectionCollapsed) {
      dismissedSelection = ''
      if (mode.value === 'rewrite') clear()
      return
    }
    const text = instance.query({ type: 'selectedText' })
    if (!text.trim()) return
    const rect = selectionRect(false)
    const key = JSON.stringify([state.selection, text, rect && Math.round(rect.left)])
    if (key !== selectionKey && key !== dismissedSelection) open('rewrite', key)
    else position()
  }

  function scheduleSelection() {
    if (!frame) frame = requestAnimationFrame(updateSelection)
  }
  function pointerDown(event) {
    if (event.target.closest('.lesson-writing')) return
    dragging = true
    clear()
    dismissedSelection = ''
  }
  function pointerUp() {
    if (!dragging) return
    dragging = false
    scheduleSelection()
  }

  onMounted(() => {
    window.addEventListener('pointerup', pointerUp)
    window.addEventListener('pointercancel', pointerUp)
    window.addEventListener('resize', position)
  })
  onBeforeUnmount(() => {
    clear()
    cancelAnimationFrame(frame)
    window.removeEventListener('pointerup', pointerUp)
    window.removeEventListener('pointercancel', pointerUp)
    window.removeEventListener('resize', position)
  })

  async function choose(option) {
    action.value = option
    error.value = ''
    position(true)
    await nextTick()
    instructionInput.value?.focus({ preventScroll: true })
  }

  function context(instance) {
    if (mode.value === 'rewrite') return { before: instance.query({ type: 'selectedText' }), after: '' }
    const { to } = instance.snapshot().selection
    // The semantic caret catches up with typing before the painted caret does.
    const point = caret.value || insertionPoint
    const paragraphs = instance.query({ type: 'paragraphs', container: to.container })
    let index = paragraphs.findIndex(({ paraId }) => paraId && (paraId === to.paraId || paraId === point?.paragraphId))
    if (index < 0 && to.path?.length === 1) index = to.path[0]
    if (index < 0 && paragraphs.length === 1) index = 0
    const join = (items) => items.map(({ text }) => text).join('\n')
    if (!paragraphs[index]) return { before: join(paragraphs.slice(0, 24)).slice(0, 14000), after: '' }
    const current = paragraphs[index].text
    const offset = point?.offset ?? to.offset ?? current.length
    return {
      before: [join(paragraphs.slice(Math.max(0, index - 18), index)), current.slice(0, offset)].filter(Boolean).join('\n').slice(-14000),
      after: [current.slice(offset), join(paragraphs.slice(index + 1, index + 8))].filter(Boolean).join('\n').slice(0, 14000),
    }
  }

  async function generate() {
    const instance = editor.value
    if (!action.value || busy.value || !instance?.snapshot().selection) return
    const selection = context(instance)
    if (mode.value === 'rewrite' && (!selection.before.trim() || selection.before.length > 14000)) {
      error.value = '请选择 1 至 14000 字的正文'
      return
    }
    const current = new AbortController()
    request = current
    revision = instance.getDocumentHandle().revision
    busy.value = true
    error.value = ''
    try {
      const result = await api('/ai/writing', {
        method: 'POST', signal: current.signal, body: {
          lesson_id: id, section: title().trim() || '教案正文', mode: mode.value,
          instruction: [action.value[1], instruction.value.trim()].filter(Boolean).join('\n'),
          ...selection,
        },
      })
      if (request !== current) return
      if (!result.text?.trim()) throw new Error('本次生成没有返回正文')
      suggestion.value = result
      instance.focus()
      await nextTick()
      position()
    } catch (failure) {
      if (request === current) error.value = failure.message
    } finally {
      if (request === current) {
        request = null
        busy.value = false
      }
    }
  }

  function apply() {
    const instance = editor.value
    const result = suggestion.value
    if (!result) return
    if (instance.getDocumentHandle().revision !== revision) {
      clear(true)
      notice.value = '正文已变化，请重新生成'
      return
    }
    instance.focus()
    const html = result.blocks?.some((block) => block.type === 'table')
      ? result.blocks.map((block) => block.type === 'table'
        ? richTable(block) : '<p>' + escapeHtml(block.text) + '</p>').join('')
      : undefined
    const outcome = instance.exec({ type: 'paste', text: html ? '' : result.text, html })
    clear()
    notice.value = outcome.ok && outcome.changed ? '已采纳 AI 建议' : '无法在当前位置写入，请选择可编辑的正文'
  }

  function documentChanged(change) {
    if (revision !== null && change.revision > revision) clear()
  }

  function keydown(event) {
    if (event.isComposing || event.keyCode === 229 || !canvas.value?.contains(event.target)) return
    const inPopup = event.target.closest('.lesson-writing')
    const shortcut = event.altKey && event.code === 'Backslash' && !event.ctrlKey && !event.metaKey && !event.repeat
    if (!inPopup && shortcut) {
      const state = editor.value?.snapshot()
      if (!state?.editable || !state.selection || state.image) return
      event.preventDefault()
      event.stopPropagation()
      if (state.selectionCollapsed) {
        open('continue')
        nextTick(() => canvas.value?.querySelector('.writing-options button')?.focus({ preventScroll: true }))
      } else scheduleSelection()
    } else if (mode.value && (event.key === 'Escape' || (suggestion.value && event.key === 'Tab' && !event.shiftKey))) {
      event.preventDefault()
      event.stopPropagation()
      if (event.key === 'Tab') apply()
      else clear(true)
    } else if (!inPopup && mode.value && (event.key.length === 1 || [
      'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown', 'Backspace', 'Delete', 'Enter',
    ].includes(event.key))) {
      clear()
    }
  }

  return { mode, action, instruction, instructionInput, suggestion, busy, error, anchor, clear, choose, generate, apply,
    position, scheduleSelection, pointerDown, keydown, documentChanged }
}
