<script setup>
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { renderFormula } from '../examMath'

const props = defineProps({ initial: { type: String, default: '' }, busy: Boolean, replace: Boolean })
const emit = defineEmits(['apply'])
const source = ref(props.initial)
const mode = ref('visual')
const container = ref(null)
const keyboardArea = ref(null)
const loading = ref(true)
const field = shallowRef(null)
const sourceInput = ref(null)
const loadError = ref('')
let active = true
let previousContainer
const templates = [
  ["分式","\\frac{#?}{#?}"],
  ["根式","\\sqrt{#?}"],
  ["上下标","{#?}_{#?}^{#?}"],
  ["积分","\\int_{#?}^{#?}{#?}\\,\\mathrm{d}x"],
  ["极限","\\lim_{x\\to #?}{#?}"],
  ["求和","\\sum_{#?}^{#?}{#?}"],
  ["向量","\\vec{#?}"],
  ["矩阵","\\begin{bmatrix}#?&#?\\\\#?&#?\\end{bmatrix}"],
  ["行列式","\\begin{vmatrix}#?&#?\\\\#?&#?\\end{vmatrix}"],
  ["方程组","\\begin{cases}#?\\\\#?\\end{cases}"],
  ["多行等式","\\begin{aligned}#?&=#?\\\\#?&=#?\\end{aligned}"],
  ["二项式","\\binom{#?}{#?}"],
]

const preview = computed(() => {
  try { return { html: renderFormula(source.value.replaceAll('#?', '{}'), true), error: '' } }
  catch { return { html: '', error: '请检查公式语法，例如括号、矩阵行列或命令是否完整。' } }
})
const canApply = computed(() => source.value.trim() && !preview.value.error && !/\\placeholder\b|#\?/.test(source.value))

onMounted(async () => {
  try {
    const { MathfieldElement } = await import('mathlive')
    if (!active) return
    MathfieldElement.locale = 'zh-CN'
    MathfieldElement.fontsDirectory = new URL('/mathlive-fonts/', location.href).href
    MathfieldElement.soundsDirectory = null
    const input = new MathfieldElement()
    input.mathVirtualKeyboardPolicy = 'manual'
    input.setAttribute('aria-label', '可视化公式')
    input.mathVirtualKeyboardLayouts = ['numeric', 'symbols', 'alphabetic', 'greek']
    input.value = source.value
    input.addEventListener('input', () => { source.value = input.value })
    previousContainer = window.mathVirtualKeyboard.container
    window.mathVirtualKeyboard.container = keyboardArea.value
    container.value.append(input)
    field.value = input
    if (mode.value === 'visual') input.focus()
  } catch {
    loadError.value = '可视化面板加载失败，可继续使用 LaTeX 输入。'
    mode.value = 'latex'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  active = false
  if (!field.value) return
  window.mathVirtualKeyboard?.hide()
  if (window.mathVirtualKeyboard) window.mathVirtualKeyboard.container = previousContainer || document.body
})

function setMode(next) {
  mode.value = next
  if (next === 'visual' && field.value) {
    field.value.value = source.value
    requestAnimationFrame(() => field.value?.focus())
  } else {
    window.mathVirtualKeyboard?.hide()
    requestAnimationFrame(() => sourceInput.value?.focus())
  }
}

function insertTemplate(template) {
  if (mode.value === 'visual' && field.value) {
    field.value.insert(template, { format: 'latex', selectionMode: 'placeholder' })
    source.value = field.value.value
    field.value.focus()
  } else {
    const input = sourceInput.value
    const start = input?.selectionStart ?? source.value.length
    const end = input?.selectionEnd ?? start
    const code = template.replaceAll('#?', '')
    source.value = source.value.slice(0, start) + code + source.value.slice(end)
    requestAnimationFrame(() => {
      if (!input) return
      const offset = template.indexOf('#?')
      const caret = start + (offset < 0 ? code.length : offset)
      input.focus()
      input.setSelectionRange(caret, caret)
    })
  }
}

function toggleKeyboard() {
  field.value?.focus()
  const keyboard = window.mathVirtualKeyboard
  if (keyboard?.visible) keyboard.hide()
  else keyboard?.show()
}

function submit() {
  if (canApply.value) emit('apply', source.value.trim())
}
</script>

<template>
  <form class="stack formula-editor" @submit.prevent="submit">
    <div class="segmented" role="group" aria-label="公式输入方式">
      <button type="button" :aria-pressed="mode === 'visual'" :disabled="!!loadError" @click="setMode('visual')">可视输入</button>
      <button type="button" :aria-pressed="mode === 'latex'" @click="setMode('latex')">LaTeX</button>
    </div>
    <p v-if="loadError" class="muted">{{ loadError }}</p>
    <div class="formula-templates" aria-label="公式模板">
      <button v-for="[name, code] of templates" :key="name" type="button" class="button subtle" @mousedown.prevent @click="insertTemplate(code)">{{ name }}</button>
    </div>
    <div v-show="mode === 'visual'" class="stack">
      <div ref="container" class="formula-mathfield"><span v-if="loading" class="muted">正在加载公式面板…</span></div>
      <button v-if="field" type="button" class="button secondary formula-keyboard-toggle" @click="toggleKeyboard">数学键盘</button>
    </div>
    <label v-if="mode === 'latex'">LaTeX 源码
      <textarea ref="sourceInput" v-model="source" rows="4" maxlength="1600" spellcheck="false" class="formula-source"></textarea>
    </label>
    <div ref="keyboardArea" class="formula-keyboard"></div>
    <div v-if="preview.html" class="formula-preview" aria-label="公式预览" v-html="preview.html"></div>
    <p v-if="preview.error" class="error" role="status">{{ preview.error }}</p>
    <div class="dialog-actions"><button type="submit" class="button primary"
      :disabled="busy || !canApply">{{ replace ? '更新公式' : '插入公式' }}</button></div>
  </form>
</template>
