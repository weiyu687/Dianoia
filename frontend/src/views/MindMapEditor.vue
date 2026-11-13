<script setup>
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, BetweenHorizontalEnd, ChevronDown, CodeXml, Download, FilePlus2, Files, FoldVertical, GitBranch,
  Image, Link2, ListTree, Maximize, MessageSquare, Minus, Palette, Paperclip, Plus, Redo2, Save, Sigma, Smile,
  SquareDashed, StickyNote, Table2, Trash2, Undo2, UnfoldVertical, Waypoints, X,
} from 'lucide-vue-next'
import { api } from '../api'
import { courseId } from '../session'
import { canvasTheme, createCanvas, editorBadges, flatNodes, fromCanvas, hyperlinkData, layouts, mapNodeLinks, mapSourceNumbers, palettes, sourceColor, toCanvas } from '../mindMapCanvas'
import { hasExportSources, mapExportOptions } from '../mindMapExport'
import MapSources from '../components/MapSources.vue'
import Modal from '../components/Modal.vue'
import '../mindMaps.css'

const MindNodeForm = defineAsyncComponent(() => import('../components/MindNodeForm.vue'))
const nodeTools = [
  { mode: 'line', label: '关联线', icon: Waypoints },
  { mode: 'summary', label: '概要', icon: BetweenHorizontalEnd, branch: true },
  { mode: 'frame', label: '外框', icon: SquareDashed, branch: true },
  { mode: 'labels', label: '标注', icon: MessageSquare },
  { mode: 'note', label: '备注', icon: StickyNote },
  { mode: 'image', label: '图片', icon: Image },
  { mode: 'icon', label: '图标', icon: Smile },
  { mode: 'hyperlink', label: '链接', icon: Link2 },
  { mode: 'nodeLinks', label: '双向链接', icon: GitBranch },
  { mode: 'attachment', label: '附件', icon: Paperclip },
  { mode: 'formula', label: '公式', icon: Sigma },
  { mode: 'table', label: '表格', icon: Table2 },
  { mode: 'code', label: '代码块', icon: CodeXml },
]
const route = useRoute()
const router = useRouter()
const template = route.name === 'mindMapTemplate'
const base = template ? '/mind-map-templates' : '/mind-maps'
const back = template ? '/mind-maps?tab=templates' : '/mind-maps'
const path = `${base}/${route.params.id}`
const item = ref(null)
const host = ref(null)
const studio = ref(null)
const title = ref('')
const documentData = ref(null)
const resources = ref([])
const selected = ref('')
const panel = ref('')
const context = ref(null)
const dialog = ref(null)
const error = ref('')
const dialogError = ref('')
const notice = ref('')
const status = ref('saved')
const exporting = ref(false)
const busy = ref(false)
const zoom = ref(100)
const nodeQuery = ref('')
const lineStart = ref('')
let engine
let resize
let theme
let timer
let pending
let savedSnapshot = ''
let closed = false
let conflicts = false

const current = computed(() => selected.value
  ? flatNodes(documentData.value.root).find(({ node }) => node.id === selected.value)?.node : null)
const outline = computed(() => flatNodes(documentData.value.root)
  .filter(({ node }) => node.text.toLowerCase().includes(nodeQuery.value.trim().toLowerCase())))
const isRoot = computed(() => current.value?.id === documentData.value?.root.id)
const panelResource = ref('')
const sourceNumbers = computed(() => documentData.value ? mapSourceNumbers(documentData.value) : new Map())
const visibleNodeSources = computed(() => current.value?.sources.filter((source) =>
  !panelResource.value || source.resource_id === panelResource.value) || [])
const canvasSelection = computed(() => selected.value.startsWith('summary-') && !current.value
  ? flatNodes(documentData.value.root).find(({ node }) => `summary-${node.id}` === selected.value)?.node
  : null)
const linkedNodes = computed(() => {
  if (!dialog.value?.node || dialog.value.mode !== 'nodeLinks') return []
  const ids = new Set(mapNodeLinks(documentData.value, dialog.value.node.id))
  return flatNodes(documentData.value.root).map(({ node }) => node).filter((node) => ids.has(node.id))
})
const targetNodes = computed(() => {
  if (!dialog.value?.node || dialog.value.mode !== 'nodeLinks') return []
  const excluded = new Set([dialog.value.node.id, ...linkedNodes.value.map((node) => node.id)])
  return flatNodes(documentData.value.root).map(({ node }) => node).filter((node) => !excluded.has(node.id))
})
const sourceLegend = computed(() => [...sourceNumbers.value].map(([id, number]) => ({ id, number })))
const dialogTitle = computed(() => {
  if (dialog.value?.mode === 'export') return '下载 PNG'
  if (dialog.value?.mode === 'template') return '存为模板'
  if (dialog.value?.mode === 'sources') return dialog.value.node ? '挂载节点资料' : '挂载整图资料'
  return nodeTools.find((tool) => tool.mode === dialog.value?.mode)?.label
})
const dark = () => document.documentElement.dataset.theme !== 'light'
const sourceLabel = (source) => resources.value.find((file) => file.id === source.resource_id)?.title || '资料已不可用'
const sourceAvailable = (source) => resources.value.some((file) => file.id === source.resource_id)
const pageLabel = ({ start, end }) => start === end ? `第 ${start} 页` : `第 ${start}–${end} 页`
const saveLabel = computed(() => ({ saved: '已保存', dirty: '待保存', saving: '正在保存', error: '保存失败', conflict: '版本冲突' })[status.value])

function snapshot() {
  return JSON.stringify({ title: title.value.trim(), document: documentData.value })
}

function scheduleSave() {
  if (closed || !item.value || snapshot() === savedSnapshot || conflicts) return
  status.value = pending ? 'saving' : 'dirty'
  clearTimeout(timer)
  timer = setTimeout(() => save(), 850)
}

function syncTree() {
  if (!engine || closed) return
  const root = fromCanvas(engine.getData())
  root.expanded = true
  documentData.value = { ...documentData.value, root }
  if (snapshot() !== savedSnapshot) scheduleSave()
  else if (!pending && !conflicts) status.value = 'saved'
}

function refreshBadges() {
  if (closed || !engine?.renderer.root) return
  const badges = editorBadges(documentData.value)
  let resizeNodes = false
  for (const { node } of flatNodes(documentData.value.root)) {
    const rendered = engine.renderer.findNodeByUid(node.id)
    if (!rendered) continue
    const tags = badges(node)
    if (JSON.stringify(rendered.getData('tag') || []) === JSON.stringify(tags)) continue
    rendered.setData({ tag: tags })
    resizeNodes = rendered.reRender() || resizeNodes
  }
  if (resizeNodes) engine.render()
}

function setSourcePanel(node, id) {
  selected.value = node.getData('uid')
  panelResource.value = id
  panel.value = 'sources'
}

function commitCanvasEditors() {
  if (!engine) return
  engine.renderer.textEdit.hideEditTextBox()
  engine.associativeLine.hideEditTextBox()
  engine.outerFrame.hideEditTextBox()
}

function save() {
  clearTimeout(timer)
  if (pending) return pending
  if (!item.value || closed || conflicts) return Promise.resolve(false)
  const contents = snapshot()
  if (contents === savedSnapshot) return Promise.resolve(true)
  if (!title.value.trim()) {
    status.value = 'error'
    error.value = '请填写文件名称'
    return Promise.resolve(false)
  }
  status.value = 'saving'
  error.value = ''
  pending = api(path, {
    method: 'PUT', body: { ...JSON.parse(contents), revision: item.value.revision },
  }).then((result) => {
    item.value = result
    savedSnapshot = contents
    status.value = snapshot() === contents ? 'saved' : 'dirty'
    return true
  }).catch((failure) => {
    conflicts = failure.status === 409
    status.value = conflicts ? 'conflict' : 'error'
    error.value = failure.message
    return false
  }).finally(() => {
    pending = null
    if (status.value === 'dirty') scheduleSave()
  })
  return pending
}

async function flush() {
  commitCanvasEditors()
  syncTree()
  if (pending && !await pending) return false
  return save()
}

function protectRefresh(event) {
  const editing = engine?.renderer.textEdit.isShowTextEdit() || engine?.associativeLine.showTextEdit || engine?.outerFrame.showTextEdit
  if (!item.value || (snapshot() === savedSnapshot && !editing)) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!item.value || await flush()) return true
  return window.confirm('修改尚未保存。确定离开编辑器？')
})

onMounted(async () => {
  try {
    const [row, files] = await Promise.all([
      api(path), template ? [] : api(`/resources?course_id=${courseId.value}`),
    ])
    if (closed) return
    if (!template && row.course_id !== courseId.value) {
      error.value = '请切换到这张导图所属的课程后重新打开'
      return
    }
    item.value = row
    title.value = row.title
    documentData.value = { ...row.document, root: fromCanvas(toCanvas(row.document.root)) }
    resources.value = files.filter((file) => file.status === 'ready' && file.page_count)
    savedSnapshot = snapshot()
    await nextTick()
    if (closed || !host.value) return
    engine = createCanvas(host.value, row.document, {
      dark: dark(),
      disabledClipboard: true,
      customCheckEnableShortcut: (event) => !event.isComposing && event.keyCode !== 229
        && !dialog.value && (event.target === host.value
          || engine?.editNodeClassList.some((name) => event.target.classList?.contains(name))),
    })
    engine.keyCommand.removeShortcut('Control+g')
    engine.on('data_change', () => {
      syncTree()
      refreshBadges()
    })
    engine.on('node_tree_render_end', refreshBadges)
    engine.on('node_active', (node, active) => {
      const id = (node || active[0])?.getData('uid') || ''
      if (selected.value !== id) panelResource.value = ''
      selected.value = id
    })
    engine.on('node_click', (target) => {
      if (!lineStart.value || target.isGeneralization || target.getData('uid') === lineStart.value) return
      const origin = engine.renderer.findNodeByUid(lineStart.value)
      lineStart.value = ''
      if (origin && (origin.getData('associativeLineTargets') || []).length < 20) {
        command('ADD_ASSOCIATIVE_LINE', origin, target)
      }
    })
    engine.on('draw_click', () => { lineStart.value = '' })
    engine.on('contextmenu', () => { lineStart.value = '' })
    engine.on('associative_line_click', () => host.value.focus())
    engine.on('outer_frame_active', () => host.value.focus())
    engine.on('node_contextmenu', (event, node) => {
      selected.value = node.getData('uid')
      const bounds = studio.value.getBoundingClientRect()
      context.value = {
        x: Math.max(5, Math.min(event.clientX - bounds.left, bounds.width - 177)),
        y: Math.max(5, Math.min(event.clientY - bounds.top, bounds.height - 280)),
      }
    })
    engine.on('node_tag_click', (node, tag) => {
      node.active()
      const id = node.getData('uid')
      if (tag.kind === 'source') setSourcePanel(node, tag.resourceId)
      else if (tag.kind === 'note') panel.value = 'note'
      else if (tag.kind) {
        const entry = flatNodes(documentData.value.root).find(({ node }) => node.id === id)?.node
        if (entry) dialog.value = { mode: tag.kind, node: entry }
      }
    })
    engine.on('view_data_change', () => { zoom.value = Math.round(engine.view.scale * 100) })
    resize = new ResizeObserver(() => { if (host.value?.clientWidth) engine.resize() })
    resize.observe(host.value)
    theme = new MutationObserver(() => engine.setThemeConfig(canvasTheme(documentData.value.palette, dark())))
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    window.addEventListener('beforeunload', protectRefresh)
  } catch (failure) { error.value = failure.message }
})

onBeforeUnmount(() => {
  closed = true
  clearTimeout(timer)
  resize?.disconnect()
  theme?.disconnect()
  engine?.destroy()
  window.removeEventListener('beforeunload', protectRefresh)
})

function command(name, ...args) {
  context.value = null
  engine?.execCommand(name, ...args)
  syncTree()
}

function nodeAction(name) {
  if (!engine) return
  if (!current.value && name === 'INSERT_CHILD_NODE') engine.renderer.root?.active()
  host.value.focus()
  command(name)
}

function pick(id) {
  command('GO_TARGET_NODE', id, (node) => node?.active())
}

function setNode(data) {
  const node = engine?.renderer.activeNodeList[0]
  if (node) {
    command('SET_NODE_STYLES', node, data)
    refreshBadges()
  }
}

function moveBranch(name) {
  const node = engine?.renderer.activeNodeList[0]
  if (node && !node.isRoot) command(name, node)
}

function setStyle(key, value) {
  const node = engine?.renderer.activeNodeList[0]
  if (node) command('SET_NODE_STYLES', node, { [key]: value })
}

function setLayout(value) {
  if (!engine) return
  documentData.value.layout = value
  engine.setLayout(value)
  engine.render(() => engine.view.fit())
  scheduleSave()
}

function setPalette(value) {
  documentData.value.palette = value
  engine.setThemeConfig(canvasTheme(value, dark()))
  scheduleSave()
}

function togglePanel(value) {
  context.value = null
  panelResource.value = ''
  panel.value = panel.value === value ? '' : value
}

function useNodeTool(mode) {
  const node = current.value || (mode === 'summary' ? canvasSelection.value : null)
  if (!node || !engine) return
  engine.renderer.textEdit.hideEditTextBox()
  context.value = null
  if (mode === 'note') { togglePanel('note'); return }
  if (mode === 'attachment') { showDialog('sources', node); return }
  if (mode === 'line') {
    if (lineStart.value) cancelLine()
    else lineStart.value = node.id
    host.value.focus()
    return
  }
  dialog.value = { mode, node }
}

function cancelLine() {
  lineStart.value = ''
}

function saveNodeDetail(value) {
  const { mode, node } = dialog.value
  const rendered = engine.renderer.findNodeByUid(node.id)
  if (!rendered) { dialog.value = null; return }
  const fields = { labels: 'mapLabels', formula: 'mapFormula', code: 'mapCode', table: 'mapTable' }
  if (fields[mode]) command('SET_NODE_STYLES', rendered, { [fields[mode]]: value })
  else if (mode === 'summary') {
    command('SET_NODE_DATA', rendered, { generalization: value ? [{ text: value, uid: `summary-${node.id}` }] : null })
    engine.render()
  } else if (mode === 'frame') {
    if (value === null) {
      const frame = node.frame?.group_id
      for (const { node: branch } of flatNodes(documentData.value.root)) {
        if (branch.frame?.group_id !== frame) continue
        const target = engine.renderer.findNodeByUid(branch.id)
        if (target) command('SET_NODE_DATA', target, { outerFrame: null })
      }
    } else if (node.frame) {
      for (const { node: branch } of flatNodes(documentData.value.root)) {
        if (branch.frame?.group_id !== node.frame.group_id) continue
        const target = engine.renderer.findNodeByUid(branch.id)
        if (target) command('SET_NODE_DATA', target, { outerFrame: { groupId: node.frame.group_id, text: value } })
      }
    } else command('ADD_OUTER_FRAME', engine.renderer.activeNodeList, { text: value })
    engine.render()
  } else if (mode === 'icon') command('SET_NODE_ICON', rendered, value ? [value] : [])
  else if (mode === 'image') command('SET_NODE_IMAGE', rendered, value ? { url: value.data_url, width: value.width, height: value.height } : { url: null })
  else if (mode === 'hyperlink') command('SET_NODE_STYLES', rendered, hyperlinkData(value))
  else if (mode === 'nodeLinks') command('SET_NODE_DATA', rendered, { mapNodeLinks: [...new Set([...node.node_links, value])].slice(0, 20) })
  refreshBadges()
  dialog.value = null
}

function unlinkNode(target) {
  const { node } = dialog.value
  const outgoing = node.node_links.includes(target)
  const originId = outgoing ? node.id : target
  const destination = outgoing ? target : node.id
  const removeLink = (origin) => {
    if (!origin) return
    command('SET_NODE_DATA', origin, {
      mapNodeLinks: (origin.getData('mapNodeLinks') || []).filter((id) => id !== destination),
    })
    refreshBadges()
  }
  const origin = engine.renderer.findNodeByUid(originId)
  if (origin) removeLink(origin)
  else command('GO_TARGET_NODE', originId, removeLink)
  dialog.value = null
}

function showDialog(mode, node = null) {
  context.value = null
  dialogError.value = ''
  dialog.value = {
    mode, node, title: `${title.value.slice(0, 155)}模板`,
    sources: JSON.parse(JSON.stringify(node?.sources || documentData.value.sources)),
  }
}

async function submitDialog() {
  if (busy.value) return
  if (dialog.value.mode === 'export') {
    const { includePages } = dialog.value
    dialog.value = null
    await exportImage(includePages)
    return
  }
  const { mode, node, sources, title: templateTitle } = dialog.value
  dialogError.value = ''
  if (mode === 'sources') {
    if (node) setNode({ mapSources: sources })
    else {
      documentData.value.sources = sources
      scheduleSave()
      refreshBadges()
    }
    dialog.value = null
    return
  }
  busy.value = true
  try {
    if (!await flush()) throw new Error(error.value || '请先保存当前导图')
    const design = await api('/mind-map-templates', { method: 'POST', body: { title: templateTitle, map_id: item.value.id } })
    dialog.value = null
    notice.value = `已存为「${design.title}」`
  } catch (failure) { dialogError.value = failure.message }
  finally { busy.value = false }
}

function openExport() {
  if (hasExportSources(documentData.value)) {
    dialogError.value = ''
    dialog.value = { mode: 'export', includePages: false }
  } else exportImage(false)
}

async function exportImage(includePages) {
  if (exporting.value || !engine) return
  exporting.value = true
  error.value = ''
  commitCanvasEditors()
  syncTree()
  const surface = document.createElement('div')
  surface.className = 'map-export-surface'
  surface.setAttribute('aria-hidden', 'true')
  document.body.appendChild(surface)
  let copy
  try {
    copy = createCanvas(surface, documentData.value, mapExportOptions(documentData.value, resources.value, includePages))
    await new Promise((resolve) => copy.render(resolve))
    const image = await copy.doExport.png()
    const link = document.createElement('a')
    link.href = image
    link.download = `${title.value.trim().replace(/[\\/:*?"<>|]/g, '_') || '思维导图'}.png`
    link.click()
  } catch { error.value = '图片导出失败，请重试' }
  finally {
    copy?.destroy()
    surface.remove()
    exporting.value = false
  }
}
</script>

<template>
  <div class="page map-editor">
    <header class="map-editor-header">
      <RouterLink class="button subtle icon-only" :to="back" aria-label="返回导图列表"><ArrowLeft :size="20" /></RouterLink>
      <template v-if="item">
        <input v-model="title" class="map-title-input" :aria-label="template ? '模板名称' : '导图名称'" maxlength="160" @input="scheduleSave">
        <span class="map-save-state" role="status" :data-state="status">{{ saveLabel }}</span>
        <div class="actions map-file-actions">
          <button class="button subtle icon-only" aria-label="立即保存" title="立即保存" @click="flush"><Save :size="18" /></button>
          <button v-if="!template" class="button secondary" @click="showDialog('template')"><FilePlus2 :size="17" /> 存为模板</button>
          <button class="button primary" :disabled="exporting" @click="openExport"><Download :size="17" /> {{ exporting ? '正在导出' : '下载 PNG' }}</button>
        </div>
      </template>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="success" role="status">{{ notice }} <RouterLink class="text-link" to="/mind-maps?tab=templates">查看模板库</RouterLink></p>
    <div v-if="!item && !error" class="empty-state" role="status">正在加载导图</div>
    <div v-if="item" class="map-workbench">
      <div class="map-toolbar" role="toolbar" aria-label="导图编辑">
        <div class="map-tools">
          <button class="button subtle icon-only" title="撤销 Ctrl+Z" aria-label="撤销" @click="command('BACK')"><Undo2 :size="17" /></button>
          <button class="button subtle icon-only" title="重做 Ctrl+Y" aria-label="重做" @click="command('FORWARD')"><Redo2 :size="17" /></button>
        </div>
        <div class="map-tools">
          <button class="button subtle" title="添加同级主题 Enter" :disabled="!current || isRoot" @click="nodeAction('INSERT_NODE')"><Plus :size="16" /> 同级主题</button>
          <button class="button subtle" title="添加子主题 Tab" @click="nodeAction('INSERT_CHILD_NODE')"><GitBranch :size="16" /> 子主题</button>
          <button class="button subtle icon-only" title="删除分支 Delete" aria-label="删除分支" :disabled="!current || isRoot" @click="command('REMOVE_NODE')"><Trash2 :size="16" /></button>
        </div>
        <div class="map-tools">
          <label class="map-layout"><span class="sr-only">布局</span><select :value="documentData.layout" @change="setLayout($event.target.value)">
            <option v-for="(label, value) in layouts" :key="value" :value="value">{{ label }}</option>
          </select></label>
          <button class="button subtle icon-only" title="全部展开" aria-label="全部展开" @click="command('EXPAND_ALL')"><UnfoldVertical :size="17" /></button>
          <button class="button subtle icon-only" title="折叠到一级分支" aria-label="折叠到一级分支" @click="command('UNEXPAND_TO_LEVEL', 2)"><FoldVertical :size="17" /></button>
        </div>
        <div class="map-tools map-panel-tools">
          <button class="button subtle" :aria-pressed="panel === 'outline'" @click="togglePanel('outline')"><ListTree :size="17" /> 大纲</button>
          <button class="button subtle" :aria-pressed="panel === 'style'" @click="togglePanel('style')"><Palette :size="17" /> 样式</button>
          <button v-if="!template" class="button subtle" :aria-pressed="panel === 'sources'" @click="togglePanel('sources')"><Files :size="17" /> 资料</button>
        </div>
      </div>
      <div class="map-insert-tools" role="toolbar" aria-label="插入到主题">
        <button v-for="tool in nodeTools.filter(({ mode }) => !template || mode !== 'attachment')" :key="tool.mode"
          type="button" class="button subtle" :disabled="(!current && !(tool.mode === 'summary' && canvasSelection)) || (tool.branch && isRoot)"
          :aria-pressed="tool.mode === 'line' ? !!lineStart : undefined" @click="useNodeTool(tool.mode)">
          <component :is="tool.icon" :size="19" />{{ tool.label }}
        </button>
      </div>
      <div ref="studio" class="map-studio" @keydown.esc="context = null; cancelLine()">
        <div ref="host" class="map-canvas" tabindex="0" role="region" aria-label="思维导图画布" @pointerdown="context = null" />
        <div v-if="lineStart" class="map-line-prompt" role="status">点击目标主题以连接 <button class="button subtle" @click="cancelLine">取消</button></div>
        <div class="map-zoom actions">
          <button class="button subtle icon-only" title="缩小" aria-label="缩小" @click="engine?.view.narrow()"><Minus :size="16" /></button>
          <span>{{ zoom }}%</span>
          <button class="button subtle icon-only" title="放大" aria-label="放大" @click="engine?.view.enlarge()"><Plus :size="16" /></button>
          <button class="button subtle icon-only" title="适应画布" aria-label="适应画布" @click="engine?.view.fit()"><Maximize :size="16" /></button>
        </div>
        <div v-if="context" class="map-context" :style="{ left: context.x + 'px', top: context.y + 'px' }">
          <button :disabled="isRoot" @click="nodeAction('INSERT_NODE')">添加同级主题</button>
          <button @click="nodeAction('INSERT_CHILD_NODE')">添加子主题</button>
          <button :disabled="isRoot" @click="nodeAction('INSERT_PARENT_NODE')">添加父主题</button>
          <button :disabled="isRoot" @click="moveBranch('UP_NODE')">上移分支</button>
          <button :disabled="isRoot" @click="moveBranch('DOWN_NODE')">下移分支</button>
          <button @click="togglePanel('note')">节点备注</button>
          <button v-if="!template" @click="showDialog('sources', current)">挂载节点资料</button>
          <button class="danger-text" :disabled="isRoot" @click="command('REMOVE_NODE')">删除分支</button>
        </div>
        <aside v-if="panel" class="map-inspector" :aria-label="({ outline: '大纲', style: '样式', note: '备注', sources: '资料' })[panel]">
          <header class="section-heading"><strong>{{ ({ outline: '导图大纲', style: '导图样式', note: '节点备注', sources: '参考资料' })[panel] }}</strong>
            <button class="button subtle icon-only" aria-label="关闭面板" @click="panel = ''"><X :size="17" /></button></header>
          <div v-if="panel === 'outline'" class="map-inspector-content stack">
            <label><span class="sr-only">搜索主题</span><input v-model="nodeQuery" type="search" placeholder="搜索主题"></label>
            <div class="map-outline">
              <button v-for="{ node, depth } in outline" :key="node.id" type="button" :style="{ paddingInlineStart: Math.min(depth, 6) * 14 + 8 + 'px' }" :aria-current="selected === node.id ? 'true' : undefined" @click="pick(node.id)">
                <ChevronDown v-if="node.children.length" :size="13" /><span>{{ node.text }}</span><Files v-if="node.sources.length" :size="13" />
              </button>
            </div>
          </div>
          <div v-else-if="panel === 'style'" class="map-inspector-content stack">
            <strong>配色主题</strong>
            <div class="map-swatches"><button v-for="(palette, key) in palettes" :key="key" class="map-swatch" :style="{ backgroundColor: palette.root }" :title="palette.label" :aria-label="palette.label" :aria-pressed="documentData.palette === key" @click="setPalette(key)" /></div>
            <template v-if="current">
              <strong>{{ current.text }}</strong>
              <label>主题形状<select :value="current.style.shape || 'roundedRectangle'" @change="setStyle('shape', $event.target.value)">
                <option value="roundedRectangle">圆角</option><option value="rectangle">矩形</option><option value="ellipse">椭圆</option><option value="diamond">菱形</option>
              </select></label>
              <label>字号<select :value="current.style.fontSize || ''" @change="setStyle('fontSize', $event.target.value ? Number($event.target.value) : undefined)">
                <option value="">主题默认</option><option v-for="size in [12, 14, 16, 18, 20, 22, 24, 28, 32, 36]" :key="size" :value="size">{{ size }}</option>
              </select></label>
              <label>字重<select :value="current.style.fontWeight || ''" @change="setStyle('fontWeight', $event.target.value || undefined)"><option value="">主题默认</option><option value="normal">常规</option><option value="bold">加粗</option></select></label>
              <div class="map-style-colors">
                <label>填充<input type="color" :value="current.style.fillColor || palettes[documentData.palette].fill" @change="setStyle('fillColor', $event.target.value)"></label>
                <label>文字<input type="color" :value="current.style.color || '#262331'" @change="setStyle('color', $event.target.value)"></label>
                <label>边框<input type="color" :value="current.style.borderColor || palettes[documentData.palette].border" @change="setStyle('borderColor', $event.target.value)"></label>
                <label>连线<input type="color" :value="current.style.lineColor || palettes[documentData.palette].root" @change="setStyle('lineColor', $event.target.value)"></label>
              </div>
              <button class="button secondary" @click="command('REMOVE_CUSTOM_STYLES')">重置节点样式</button>
            </template>
            <p v-else class="muted">选中主题后可调整节点样式。</p>
          </div>
          <div v-else-if="panel === 'note'" class="map-inspector-content stack">
            <label v-if="current" :key="current.id">{{ current.text }}<textarea :value="current.note" rows="7" maxlength="2000" placeholder="添加教学提示或补充说明" @input="setNode({ mapNote: $event.target.value })"></textarea></label>
            <p v-else class="muted">请选择要备注的主题。</p>
          </div>
          <div v-else class="map-inspector-content stack">
            <template v-if="sourceLegend.length">
              <strong>资料编号</strong>
              <div v-for="{ id, number } in sourceLegend" :key="id" class="map-source-legend">
                <span :style="{ background: sourceColor(number) }">{{ number }}</span><span>{{ sourceLabel({ resource_id: id }) }}</span>
              </div>
            </template>
            <div class="section-heading"><strong>整图资料</strong><button class="button secondary" @click="showDialog('sources')">管理</button></div>
            <p v-if="!documentData.sources.length" class="muted">暂无整图资料。</p>
            <div v-for="(source, index) in documentData.sources" :key="index" class="map-reference">
              <RouterLink v-if="sourceAvailable(source)" class="text-link" :to="{ name: 'resource', params: { id: source.resource_id }, query: { page: source.start } }" target="_blank">{{ sourceLabel(source) }} · {{ pageLabel(source) }}</RouterLink>
              <span v-else class="muted">{{ sourceLabel(source) }} · {{ pageLabel(source) }}</span>
            </div>
            <template v-if="current">
              <div class="section-heading"><strong>节点资料</strong><button class="button secondary" @click="showDialog('sources', current)">管理</button></div>
              <p class="muted">{{ current.text }}</p>
              <button v-if="panelResource && visibleNodeSources.length !== current.sources.length" class="button subtle" @click="panelResource = ''">显示全部节点资料</button>
              <p v-if="!visibleNodeSources.length" class="muted">暂无节点资料。</p>
              <div v-for="(source, index) in visibleNodeSources" :key="index" class="map-reference">
                <RouterLink v-if="sourceAvailable(source)" class="text-link" :to="{ name: 'resource', params: { id: source.resource_id }, query: { page: source.start } }" target="_blank">{{ sourceLabel(source) }} · {{ pageLabel(source) }}</RouterLink>
                <span v-else class="muted">{{ sourceLabel(source) }} · {{ pageLabel(source) }}</span>
              </div>
            </template>
          </div>
        </aside>
      </div>
      <footer class="map-footer"><span>{{ flatNodes(documentData.root).length }} 个主题</span><span><kbd>Tab</kbd> 子主题 <kbd>Enter</kbd> 同级主题 <kbd>Shift</kbd> + <kbd>Enter</kbd> 节点内换行</span></footer>
    </div>
    <Modal :open="!!dialog" :wide="['sources', 'table', 'code'].includes(dialog?.mode)" :title="dialogTitle" @close="!busy && (dialog = null)">
      <MindNodeForm v-if="dialog?.node && dialog.mode !== 'sources'" :key="`${dialog.mode}:${dialog.node.id}`"
        :mode="dialog.mode" :node="dialog.node" :targets="targetNodes" :linked="linkedNodes"
        @save="saveNodeDetail" @cancel="dialog = null" @unlink="unlinkNode" @jump="(id) => { dialog = null; pick(id) }" />
      <form v-else-if="dialog" class="stack" @submit.prevent="submitDialog">
        <MapSources v-if="dialog.mode === 'sources'" v-model="dialog.sources" :resources="resources" />
        <template v-else-if="dialog.mode === 'export'">
          <label class="map-export-checkbox"><input v-model="dialog.includePages" type="checkbox" aria-describedby="map-export-help"> 标注参考资料页码</label>
          <p id="map-export-help" class="muted">资料名称集中列在图底。引用多份资料时，用编号区分各节点的页码来源。</p>
        </template>
        <template v-else><label>模板名称<input v-model.trim="dialog.title" required maxlength="160"></label><p class="muted">模板保留当前结构、文字和样式。课程资料引用留在原导图。</p></template>
        <p v-if="dialogError" class="error" role="alert">{{ dialogError }}</p>
        <div class="dialog-actions"><button type="button" class="button secondary" :disabled="busy" @click="dialog = null">取消</button><button type="submit" class="button primary" :disabled="busy">{{ dialog.mode === 'export' ? '下载' : busy ? '正在保存' : '保存' }}</button></div>
      </form>
    </Modal>
  </div>
</template>
