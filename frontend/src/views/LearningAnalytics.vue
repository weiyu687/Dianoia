<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { Activity, AlertCircle, ArrowDownToLine, BarChart3, BookOpenCheck, Check, ChevronRight, CircleHelp, Clock3, FileSpreadsheet, Layers3, LineChart as LineChartIcon, LoaderCircle, Plus, RefreshCw, Search, Sparkles, Trash2, Upload, Users, X } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import { course, courseId } from '../session'
import { useRoute } from 'vue-router'

echarts.use([BarChart, LineChart, PieChart, GridComponent, TooltipComponent, LegendComponent, GraphicComponent, CanvasRenderer])

const route = useRoute()
const view = ref('dashboard')
const error = ref('')
const success = ref('')
const busy = ref(false)
const loading = ref(true)
const context = ref({ classes: [], batches: [] })
const dashboard = ref(null)
const imports = ref([])
const plans = ref([])
const mappings = ref([])
const dashboardTemplates = ref([])
const dashboardPanels = ref(['metrics', 'trend', 'distribution', 'categories', 'students'])
const activeDashboardTemplate = ref('class-overview')
const publishables = ref([])
const shared = ref([])
const activeClass = ref('')
const activeBatch = ref('')
const activeMetric = ref('')
const fileInput = ref(null)
const draft = ref(null)
const mapping = ref(null)
const previewIssues = ref([])
const activePlan = ref(null)
const planScope = ref('class')
const planStudent = ref('')
const planFocus = ref('')
const selectedResources = ref([])
const resourceQuery = ref('')
const publishSource = ref('')
const publishMeta = ref({ title: '', summary: '', subject: '', academic_level: '', term_label: '', section: '', keywords: '' })
const studentPanel = ref(null)
const studentView = ref('')
const trendEl = ref(null)
const distributionEl = ref(null)
const categoriesEl = ref(null)
let trendChart
let distributionChart
let categoriesChart
let resizeObserver
let pollTimer

const tabs = [
  { id: 'dashboard', label: '学情大屏', icon: BarChart3 },
  { id: 'imports', label: '数据导入', icon: FileSpreadsheet },
  { id: 'plans', label: '计划与资源', icon: Sparkles },
]
const statusNames = { mapping: '待映射', queued: '排队中', processing: '处理中', ready: '已入库', failed: '失败' }
const className = (code) => context.value.classes.find((item) => item.code === code)?.name || code
const students = computed(() => dashboard.value?.students || [])
const showMetricCards = computed(() => dashboardPanels.value.some((panel) => ['metrics', 'score', 'attendance'].includes(panel)))
const showCategoryChart = computed(() => dashboardPanels.value.includes('categories') || dashboardPanels.value.includes('attendance'))
const canGeneratePlan = computed(() => !!dashboard.value?.batch && (planScope.value === 'class' || planStudent.value))
const filteredShared = computed(() => shared.value.filter((row) => !resourceQuery.value ||
  `${row.title} ${row.summary} ${row.subject} ${row.section} ${(row.keywords || []).join(' ')}`.toLowerCase().includes(resourceQuery.value.toLowerCase())))

function resetNotices() { error.value = ''; success.value = '' }
function queryString(values) {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== null && value !== '') params.set(key, value) })
  return params.toString()
}

async function loadContext() {
  context.value = await api(`/learning-analytics/context?course_id=${courseId.value}`)
  imports.value = context.value.batches || []
}

async function loadDashboard() {
  const query = queryString({ course_id: courseId.value, class_code: activeClass.value, batch_id: activeBatch.value, metric: activeMetric.value })
  dashboard.value = await api(`/learning-analytics/dashboard?${query}`)
  if (dashboard.value?.batch) {
    activeBatch.value = dashboard.value.batch.id
    if (!activeMetric.value || !dashboard.value.metrics.some((item) => item.key === activeMetric.value)) {
      activeMetric.value = dashboard.value.metrics[0]?.key || ''
    }
  }
  await nextTick()
  renderCharts()
  if (trendEl.value) resizeObserver?.observe(trendEl.value)
  if (distributionEl.value) resizeObserver?.observe(distributionEl.value)
  if (categoriesEl.value) resizeObserver?.observe(categoriesEl.value)
}

async function loadImports() {
  imports.value = await api(`/learning-analytics/imports?course_id=${courseId.value}`)
  context.value.batches = imports.value
}

async function loadPlans() {
  plans.value = await api(`/learning-analytics/plans?course_id=${courseId.value}`)
}

async function loadMappings() { mappings.value = await api('/learning-analytics/mapping-templates') }

async function loadDashboardTemplates() {
  dashboardTemplates.value = await api('/learning-analytics/dashboard-templates')
  selectDashboardTemplate(activeDashboardTemplate.value)
}

async function loadShared() { shared.value = await api('/learning-analytics/shared-resources?limit=200') }

async function loadPublishables() { publishables.value = await api(`/learning-analytics/publishables?course_id=${courseId.value}`) }

async function loadAll() {
  loading.value = true
  resetNotices()
  try {
    await Promise.all([loadContext(), loadImports(), loadPlans(), loadMappings(), loadDashboardTemplates(), loadShared(), loadPublishables()])
    await loadDashboard()
    if (imports.value.some((item) => ['queued', 'processing'].includes(item.status))) startPolling()
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false; await nextTick(); renderCharts() }
}

function getChartTheme() {
  const styles = getComputedStyle(document.documentElement)
  return { text: styles.getPropertyValue('--text').trim(), muted: styles.getPropertyValue('--muted').trim(),
    line: styles.getPropertyValue('--line').trim(), accent: styles.getPropertyValue('--accent').trim(),
    raised: styles.getPropertyValue('--raised').trim() }
}

function renderCharts() {
  if (!trendEl.value || !distributionEl.value || !categoriesEl.value) return
  const theme = getChartTheme()
  trendChart ||= echarts.init(trendEl.value)
  distributionChart ||= echarts.init(distributionEl.value)
  categoriesChart ||= echarts.init(categoriesEl.value)
  const history = dashboard.value?.history || []
  trendChart.setOption({
    color: [theme.accent], animationDuration: 320, grid: { left: 42, right: 20, top: 22, bottom: 38 },
    tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: history.map((item) => item.term_label || item.title), axisLabel: { color: theme.muted, hideOverlap: true }, axisLine: { lineStyle: { color: theme.line } } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: theme.muted }, splitLine: { lineStyle: { color: theme.line } } },
    series: [{ type: 'line', smooth: true, data: history.map((item) => item.average), connectNulls: false,
      symbolSize: 8, areaStyle: { opacity: .09 }, lineStyle: { width: 3 }, itemStyle: { borderWidth: 2, borderColor: theme.raised } }],
    graphic: history.length ? [] : [{ type: 'text', left: 'center', top: 'middle', style: { text: '导入更多批次后显示历史变化', fill: theme.muted, fontSize: 13 } }],
  }, true)
  const distribution = dashboard.value?.distribution || []
  distributionChart.setOption({
    color: ['#8872da'], grid: { left: 42, right: 18, top: 22, bottom: 35 }, tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: distribution.map((item) => item.label), axisLabel: { color: theme.muted }, axisLine: { lineStyle: { color: theme.line } } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { color: theme.muted }, splitLine: { lineStyle: { color: theme.line } } },
    series: [{ type: 'bar', barMaxWidth: 38, data: distribution.map((item) => item.value), itemStyle: { borderRadius: [6, 6, 0, 0] } }],
    graphic: distribution.length ? [] : [{ type: 'text', left: 'center', top: 'middle', style: { text: '选择成绩指标后显示分布', fill: theme.muted, fontSize: 13 } }],
  }, true)
  const categories = dashboard.value?.categories || []
  categoriesChart.setOption({
    color: ['#6289d9', '#64b5a1', '#e7ab60', '#bc78b9', '#d77879', '#60a4c7', '#9a8bd2', '#7eaa63'],
    tooltip: { trigger: 'item' }, legend: { bottom: 0, textStyle: { color: theme.muted }, type: 'scroll' },
    series: [{ type: 'pie', radius: ['43%', '72%'], center: ['50%', '44%'], avoidLabelOverlap: true,
      itemStyle: { borderColor: theme.raised, borderWidth: 3 }, label: { color: theme.text, formatter: '{b}\n{d}%' }, data: categories.map((item) => ({ name: item.label, value: item.value })) }],
    graphic: categories.length ? [] : [{ type: 'text', left: 'center', top: 'middle', style: { text: '分类指标分布会显示在这里', fill: theme.muted, fontSize: 13 } }],
  }, true)
}

function startPolling() {
  clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    try {
      const before = imports.value.map((item) => `${item.id}:${item.status}:${item.processed_count}`).join('|')
      await loadImports()
      const after = imports.value.map((item) => `${item.id}:${item.status}:${item.processed_count}`).join('|')
      if (before !== after) {
        const current = imports.value.find((item) => item.id === draft.value?.id)
        if (current && draft.value) draft.value = current
        await loadDashboard()
      }
      if (!imports.value.some((item) => ['queued', 'processing'].includes(item.status))) clearInterval(pollTimer)
    } catch { clearInterval(pollTimer) }
  }, 2400)
}

function changeView(value) {
  if (value !== 'dashboard') {
    trendChart?.dispose(); distributionChart?.dispose(); categoriesChart?.dispose()
    trendChart = distributionChart = categoriesChart = null
    resizeObserver?.disconnect()
  }
  view.value = value
  resetNotices()
  if (value === 'imports') { loadImports(); loadMappings() }
  if (value === 'plans') { loadPlans(); loadShared(); loadPublishables() }
}

function openFilePicker() { fileInput.value?.click() }

function updateMappingSuggestion(suggested) {
  mapping.value = structuredClone(suggested || { student_code: '', student_name: null, occurred_at: null, activity: null,
    knowledge_tag: null, maximum_column: null, metrics: [] })
}

async function uploadFile(event) {
  resetNotices()
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  busy.value = true
  try {
    const form = new FormData()
    form.set('course_id', courseId.value)
    form.set('class_code', activeClass.value)
    form.set('term_label', '')
    form.set('title', file.name.replace(/\.[^.]+$/, ''))
    form.set('file', file)
    const result = await api('/learning-analytics/imports/preview', { method: 'POST', body: form })
    draft.value = result
    updateMappingSuggestion(result.suggested_mapping)
    previewIssues.value = []
    view.value = 'imports'
    await loadImports()
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function chooseSheet() {
  if (!draft.value) return
  busy.value = true
  resetNotices()
  try {
    const result = await api(`/learning-analytics/imports/${draft.value.id}/sheet`, { method: 'PUT', body: { sheet_name: draft.value.sheet_name } })
    draft.value = result
    updateMappingSuggestion(result.suggested_mapping)
    previewIssues.value = []
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

function addMetric() {
  if (!mapping.value || mapping.value.metrics.length >= 12) return
  const column = draft.value.columns.find((item) => !mapping.value.metrics.some((metric) => metric.column === item)) || draft.value.columns[0]
  mapping.value.metrics.push({ column, label: column, kind: 'score', maximum: null })
}

async function applyMappingTemplate(event) {
  const id = event.target.value
  const template = mappings.value.find((item) => item.id === id)
  if (!template) return
  if (template.builtin) {
    const kind = { 'builtin-score': 'score', 'builtin-homework': 'homework', 'builtin-attendance': 'attendance' }[id]
    if (kind && mapping.value) mapping.value.metrics = mapping.value.metrics.map((metric) => ({
      ...metric, kind, maximum: kind === 'score' ? (metric.maximum || 100) : null,
    }))
    event.target.value = ''
    return
  }
  if (!template.config) return
  const config = structuredClone(template.config)
  if ([config.student_code, ...config.metrics.map((item) => item.column)].some((column) => !draft.value.columns.includes(column))) {
    error.value = '此模板的列名与当前工作表不匹配。请继续手动选择字段。'
    return
  }
  mapping.value = config
}

function selectDashboardTemplate(id) {
  const template = dashboardTemplates.value.find((item) => item.id === id)
  if (!template) return
  activeDashboardTemplate.value = id
  dashboardPanels.value = [...(template.config?.panels || ['metrics', 'trend', 'distribution', 'categories', 'students'])]
}

async function saveDashboardTemplate() {
  const title = prompt('为当前大屏布局命名')
  if (!title?.trim()) return
  try {
    const result = await api('/learning-analytics/dashboard-templates', { method: 'POST', body: {
      title: title.trim(), config: { panels: [...dashboardPanels.value] },
    } })
    await loadDashboardTemplates()
    selectDashboardTemplate(result.id)
    success.value = '大屏布局已保存。'
  } catch (failure) { error.value = failure.message }
}

async function deleteDashboardTemplate() {
  const template = dashboardTemplates.value.find((item) => item.id === activeDashboardTemplate.value)
  if (!template || template.builtin || !confirm(`删除大屏模板「${template.title}」？`)) return
  try {
    await api(`/learning-analytics/dashboard-templates/${template.id}`, { method: 'DELETE' })
    activeDashboardTemplate.value = 'class-overview'
    await loadDashboardTemplates()
    success.value = '大屏模板已删除。'
  } catch (failure) { error.value = failure.message }
}

async function saveMapping() {
  resetNotices()
  busy.value = true
  try {
    const metadata = await api(`/learning-analytics/imports/${draft.value.id}`, { method: 'PUT', body: {
      title: draft.value.title, class_code: draft.value.class_code || null, term_label: draft.value.term_label || '',
    } })
    draft.value = metadata
    const result = await api(`/learning-analytics/imports/${draft.value.id}/mapping`, { method: 'PUT', body: mapping.value })
    draft.value = result
    previewIssues.value = result.validation?.issues || []
    success.value = `字段映射已保存：${result.valid_count} 条有效记录，${result.invalid_count} 条需核对。`
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function confirmImport() {
  resetNotices()
  busy.value = true
  try {
    draft.value = await api(`/learning-analytics/imports/${draft.value.id}`, { method: 'PUT', body: {
      title: draft.value.title, class_code: draft.value.class_code || null, term_label: draft.value.term_label || '',
    } })
    draft.value = await api(`/learning-analytics/imports/${draft.value.id}/confirm`, { method: 'POST' })
    success.value = '数据已加入后台处理队列。处理完成后，统计大屏会自动更新。'
    await loadImports()
    startPolling()
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function retryImport(item) {
  resetNotices()
  try {
    const result = await api(`/learning-analytics/imports/${item.id}/retry`, { method: 'POST' })
    if (draft.value?.id === result.id) draft.value = result
    await loadImports()
    startPolling()
  } catch (failure) { error.value = failure.message }
}

async function removeImport(item) {
  if (!confirm(`删除「${item.title}」及其统计记录？此操作不能撤销。`)) return
  resetNotices()
  try {
    await api(`/learning-analytics/imports/${item.id}`, { method: 'DELETE' })
    if (draft.value?.id === item.id) { draft.value = null; mapping.value = null }
    await Promise.all([loadImports(), loadDashboard()])
    success.value = '导入记录与统计数据已删除。'
  } catch (failure) { error.value = failure.message }
}

async function saveMappingTemplate() {
  if (!draft.value || !mapping.value) return
  const title = prompt('为当前字段映射命名')
  if (!title?.trim()) return
  try {
    const kind = mapping.value.metrics.some((item) => item.kind === 'attendance') ? 'attendance'
      : mapping.value.metrics.some((item) => item.kind === 'homework') ? 'homework' : 'score'
    await api('/learning-analytics/mapping-templates', { method: 'POST', body: { title: title.trim(), category: kind, config: mapping.value } })
    await loadMappings()
    success.value = '映射模板已保存。'
  } catch (failure) { error.value = failure.message }
}

function openStudent(row) {
  planScope.value = 'student'
  planStudent.value = row.student_code
  studentView.value = row.student_code
  loadStudent(row.student_code)
}

async function loadStudent(code) {
  try {
    studentPanel.value = await api(`/learning-analytics/students/${encodeURIComponent(code)}?${queryString({ course_id: courseId.value, class_code: activeClass.value })}`)
  } catch (failure) { error.value = failure.message }
}

function closeStudentPanel() { studentPanel.value = null; studentView.value = '' }

function prepareStudentPlan() {
  planStudent.value = studentPanel.value?.student_code || studentView.value
  planScope.value = 'student'
  closeStudentPanel()
  changeView('plans')
}

async function createPlan() {
  resetNotices()
  busy.value = true
  try {
    const item = await api('/learning-analytics/plans', { method: 'POST', body: {
      course_id: Number(courseId.value), class_code: activeClass.value || null, scope: planScope.value,
      student_code: planScope.value === 'student' ? planStudent.value : null, focus: planFocus.value,
      batch_ids: activeBatch.value ? [activeBatch.value] : [], resource_ids: selectedResources.value,
    } })
    await loadPlans()
    activePlan.value = item
    view.value = 'plans'
    success.value = item.generation_source === 'ai' ? 'AI 计划草稿已生成，请核对并编辑。' : '数据摘要已生成规则版计划草稿，当前模型不可用；请继续编辑。'
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function savePlan() {
  if (!activePlan.value) return
  resetNotices()
  busy.value = true
  try {
    activePlan.value = await api(`/learning-analytics/plans/${activePlan.value.id}`, { method: 'PUT', body: {
      title: activePlan.value.title, focus: activePlan.value.focus, content: activePlan.value.content,
      resource_ids: activePlan.value.resource_ids || [],
    } })
    await loadPlans()
    success.value = '计划草稿已保存。'
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function selectPlan(item) {
  activePlan.value = await api(`/learning-analytics/plans?course_id=${courseId.value}`).then((rows) => rows.find((row) => row.id === item.id) || item)
}

async function removePlan(item) {
  if (!confirm(`删除计划草稿「${item.title}」？`)) return
  try {
    await api(`/learning-analytics/plans/${item.id}`, { method: 'DELETE' })
    if (activePlan.value?.id === item.id) activePlan.value = null
    await loadPlans()
  } catch (failure) { error.value = failure.message }
}

function fillPublishMeta(source) {
  publishSource.value = source ? `${source.source_type}:${source.id}` : ''
  publishMeta.value = source ? { title: source.title, summary: '', subject: course.value?.name || '',
    academic_level: '', term_label: '', section: '', keywords: '' } : { title: '', summary: '', subject: course.value?.name || '',
    academic_level: '', term_label: '', section: '', keywords: '' }
}

async function publishResource() {
  const [source_type, source_id] = publishSource.value.split(':')
  if (!source_type || !source_id) return
  resetNotices()
  busy.value = true
  try {
    await api('/learning-analytics/shared-resources', { method: 'POST', body: {
      course_id: Number(courseId.value), source_type, source_id, title: publishMeta.value.title,
      summary: publishMeta.value.summary, subject: publishMeta.value.subject,
      academic_level: publishMeta.value.academic_level, term_label: publishMeta.value.term_label,
      section: publishMeta.value.section, keywords: publishMeta.value.keywords.split(/[，,、]/).map((item) => item.trim()).filter(Boolean),
    } })
    await loadShared()
    success.value = '资源已发布到平台共享资源池。'
    fillPublishMeta(null)
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function withdrawResource(item) {
  if (!confirm(`从共享资源池下架「${item.title}」？`)) return
  try {
    await api(`/learning-analytics/shared-resources/${item.id}`, { method: 'DELETE' })
    await loadShared()
    success.value = '资源已下架。'
  } catch (failure) { error.value = failure.message }
}

watch([activeClass, activeBatch, activeMetric], async () => {
  if (!loading.value) {
    activeMetric.value && await loadDashboard()
    if (!activeMetric.value) await loadDashboard()
  }
})
watch(() => dashboard.value, async () => { await nextTick(); renderCharts() }, { deep: true })
watch(dashboardPanels, async () => {
  await nextTick()
  trendChart?.dispose(); distributionChart?.dispose(); categoriesChart?.dispose()
  trendChart = distributionChart = categoriesChart = null
  renderCharts()
}, { deep: true })

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => { trendChart?.resize(); distributionChart?.resize(); categoriesChart?.resize() })
  await loadAll()
  const planId = String(route.query.plan || '')
  const plan = plans.value.find((item) => item.id === planId)
  if (plan) {
    view.value = 'plans'
    await selectPlan(plan)
  }
})
onBeforeUnmount(() => {
  clearInterval(pollTimer)
  resizeObserver?.disconnect()
  trendChart?.dispose()
  distributionChart?.dispose()
  categoriesChart?.dispose()
})
</script>

<template>
  <div class="page analytics-page">
    <header class="analytics-heading">
      <div><div class="eyebrow"><Activity :size="15" /> 教学数据工作台</div><h1>学情分析</h1>
        <p>导入成绩、作业与考勤表格，按数据来源查看班级变化，并将分析整理为可编辑的教学计划。</p></div>
      <div class="actions"><button class="button secondary" @click="loadAll"><RefreshCw :size="16" />刷新</button>
        <button class="button primary" @click="changeView('imports'); openFilePicker()"><Upload :size="16" />导入数据</button></div>
    </header>

    <div class="segmented analytics-tabs" role="tablist" aria-label="学情分析功能">
      <button v-for="item in tabs" :key="item.id" :aria-pressed="view === item.id" @click="changeView(item.id)"><component :is="item.icon" :size="16" />{{ item.label }}</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p><p v-if="success" class="success" role="status">{{ success }}</p>
    <div v-if="loading" class="panel analytics-loading"><LoaderCircle class="spin" :size="22" />正在读取当前课程数据</div>

    <template v-else-if="view === 'dashboard'">
      <section class="panel analytics-filters">
        <div><span class="muted">分析范围</span><div class="segmented"><button :aria-pressed="!activeClass" @click="activeClass = ''"><Layers3 :size="15" />全部班级</button>
          <button v-for="group in context.classes" :key="group.code" :aria-pressed="activeClass === group.code" @click="activeClass = group.code">{{ group.name }}</button></div></div>
        <label>数据批次<select v-model="activeBatch"><option value="">最新一批可用数据</option><option v-for="item in imports.filter((row) => row.status === 'ready')" :key="item.id" :value="item.id">{{ item.title }} · {{ item.term_label || '未标学期' }}</option></select></label>
        <label v-if="dashboard?.metrics?.length">分析指标<select v-model="activeMetric"><option v-for="metric in dashboard.metrics" :key="metric.key" :value="metric.key">{{ metric.label }} · {{ metric.entries }} 条</option></select></label>
      </section>
      <section class="panel analytics-layout-tools">
        <label>大屏模板<select :value="activeDashboardTemplate" @change="selectDashboardTemplate($event.target.value)"><option v-for="item in dashboardTemplates" :key="item.id" :value="item.id">{{ item.title }}{{ item.builtin ? '（内置）' : '' }}</option></select></label>
        <div class="analytics-panel-toggles"><span class="muted">显示面板</span><label v-for="item in [{ key: 'metrics', label: '指标卡' }, { key: 'trend', label: '历史趋势' }, { key: 'distribution', label: '成绩分布' }, { key: 'categories', label: '类别构成' }, { key: 'students', label: '学生记录' }]" :key="item.key"><input v-model="dashboardPanels" type="checkbox" :value="item.key">{{ item.label }}</label></div>
        <div class="actions"><button class="button secondary" @click="saveDashboardTemplate"><Layers3 :size="15" />保存为模板</button><button v-if="dashboardTemplates.find((item) => item.id === activeDashboardTemplate && !item.builtin)" class="button subtle danger-text" @click="deleteDashboardTemplate"><Trash2 :size="14" />删除模板</button></div>
      </section>
      <template v-if="dashboard?.batch">
        <div class="analytics-source-line"><span class="status-tag ready"><Check :size="13" /> 已入库</span><span>{{ dashboard.batch.title }}</span>
          <span>{{ dashboard.batch.term_label || '未标注学期' }}</span><span>有效记录 {{ dashboard.batch.valid_count }}</span>
          <button class="button subtle" @click="changeView('imports')">查看导入详情 <ChevronRight :size="15" /></button></div>
        <section v-if="showMetricCards" class="analytics-kpis">
          <article class="panel"><span>覆盖学生</span><strong>{{ dashboard.summary.students || 0 }}</strong><small>按当前指标统计</small></article>
          <article class="panel"><span>{{ dashboard.selected_metric?.kind === 'score' ? '成绩均值' : dashboard.selected_metric?.kind === 'attendance' ? '出勤率' : dashboard.selected_metric?.kind === 'homework' ? '完成率' : '数值均值' }}</span>
            <strong>{{ dashboard.selected_metric?.kind === 'attendance' || dashboard.selected_metric?.kind === 'homework' ? (dashboard.summary.rate == null ? '—' : `${dashboard.summary.rate}%`) : dashboard.summary.average == null ? '—' : dashboard.summary.average }}</strong>
            <small v-if="dashboard.summary.normalized_average != null">标准化到百分制 {{ dashboard.summary.normalized_average }} 分</small><small v-else>按原始指标口径统计</small></article>
          <article class="panel"><span>有效指标记录</span><strong>{{ dashboard.summary.entries || 0 }}</strong><small>缺失值不会按 0 分处理</small></article>
          <article class="panel"><span>需要复核行</span><strong>{{ dashboard.batch.invalid_count || 0 }}</strong><small>上传预览阶段可查看原因</small></article>
        </section>
        <section class="analytics-chart-grid">
          <article v-show="dashboardPanels.includes('trend')" class="panel analytics-chart-card"><div class="section-heading"><div><h2><LineChartIcon :size="18" />历史变化</h2><p>同一指标在最近批次中的均值；量纲不同的指标不合并。</p></div><span class="muted">{{ dashboard.history.length }} 个批次</span></div><div ref="trendEl" class="analytics-chart"></div></article>
          <article v-show="dashboardPanels.includes('distribution')" class="panel analytics-chart-card"><div class="section-heading"><div><h2><BarChart3 :size="18" />成绩分布</h2><p>有明确满分口径时按百分制分组。</p></div></div><div ref="distributionEl" class="analytics-chart short"></div></article>
          <article v-show="showCategoryChart" class="panel analytics-chart-card"><div class="section-heading"><div><h2><Activity :size="18" />类别构成</h2><p>适用于提交状态、考勤状态等分类数据。</p></div></div><div ref="categoriesEl" class="analytics-chart short"></div></article>
          <article class="panel analytics-note-card"><div class="note-icon"><CircleHelp :size="19" /></div><div><h2>指标口径说明</h2><p>系统只按已确认的字段映射汇总，不训练或输出学生能力预测。成绩跨批次比较时优先使用满分换算后的百分制；没有满分信息的指标保留原始口径。</p>
            <p v-if="dashboard.batch.invalid_count">当前批次有 {{ dashboard.batch.invalid_count }} 行未通过基础检查，可在导入详情中复核。</p></div></article>
        </section>
        <section v-if="dashboardPanels.includes('students')" class="panel analytics-students">
          <header class="section-heading"><div><h2><Users :size="18" />学生表现</h2><p>按当前指标和所选数据范围列出，不进行自动排名。</p></div><button class="button secondary" @click="planScope = 'class'; changeView('plans')"><Sparkles :size="15" />生成班级计划草稿</button></header>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>学生</th><th>记录数</th><th>均值</th><th>最近一次</th><th>时间</th><th></th></tr></thead>
            <tbody><tr v-for="item in students" :key="item.student_code"><td><button class="analytics-student-link" @click="openStudent(item)"><strong>{{ item.student_name || '未提供姓名' }}</strong><small>{{ item.student_code }}</small></button></td><td>{{ item.entries }}</td><td>{{ item.normalized_average ?? item.average ?? '—' }}</td><td>{{ (item.latest_value ?? item.latest_text) || '—' }}</td><td>{{ item.latest_at ? formatDate(item.latest_at) : '—' }}</td><td><button class="button subtle" @click="openStudent(item)">查看 <ChevronRight :size="14" /></button></td></tr>
              <tr v-if="!students.length"><td colspan="6" class="analytics-empty-row">这批数据没有可展示的学生记录。</td></tr></tbody></table></div>
        </section>
      </template>
      <section v-else class="panel analytics-empty"><div class="empty-art"><BarChart3 :size="28" /></div><h2>先导入一份表格，开始查看学情</h2><p>支持成绩、作业与考勤数据，可使用 CSV、XLS 或 XLSX 文件。上传后选择学生标识和要分析的指标。</p><button class="button primary" @click="changeView('imports'); openFilePicker()"><Upload :size="16" />选择表格</button>
        <div class="analytics-empty-files"><span>可先下载示例文件</span><a href="/test-data/learning-analytics/课程学情综合示例.xlsx" download>多工作表 XLSX</a><a href="/test-data/learning-analytics/成绩示例-UTF8.csv" download>UTF-8 CSV</a><a href="/test-data/learning-analytics/作业示例-GB18030.csv" download>GB18030 CSV</a></div></section>
    </template>

    <template v-else-if="view === 'imports'">
      <section class="analytics-import-layout">
        <article class="panel analytics-import-main">
          <div class="section-heading"><div><h2><FileSpreadsheet :size="19" />导入表格</h2><p>支持 CSV、旧版 XLS 和 XLSX；先预览，再确认写入统计库。</p></div>
            <button class="button primary" :disabled="busy" @click="openFilePicker"><Upload :size="15" />选择文件</button></div>
          <div class="analytics-upload-strip"><FileSpreadsheet :size="20" /><span>文件最大 20 MB；每个工作表最多 50,000 行、100 列。公式按文件缓存值读取，不执行宏。</span>
            <div class="analytics-empty-files"><a href="/test-data/learning-analytics/课程学情综合示例.xlsx" download>下载 XLSX 示例</a><a href="/test-data/learning-analytics/成绩示例-UTF8.csv" download>CSV 示例</a></div></div>
          <template v-if="draft">
            <div class="analytics-draft-heading"><div><span class="status-tag">{{ draft.extension?.toUpperCase() }}</span><strong>{{ draft.title }}</strong><small>{{ draft.original_filename }} · {{ draft.row_count }} 行 · {{ draft.columns?.length }} 列</small></div>
              <button class="button subtle icon-only" aria-label="关闭当前预览" @click="draft = null; mapping = null"><X :size="17" /></button></div>
            <div class="analytics-draft-meta"><label>资料名称<input v-model="draft.title" maxlength="160"></label><label>学期/阶段<input v-model="draft.term_label" placeholder="如：2026 秋季学期 / 第 3 周"></label>
              <label>班级（可选）<select v-model="draft.class_code"><option value="">不限定单个班级</option><option v-for="item in context.classes" :key="item.code" :value="item.code">{{ item.name }}</option></select></label>
              <label v-if="draft.sheet_names?.length">选择工作表<select v-model="draft.sheet_name" @change="chooseSheet"><option v-for="sheet in draft.sheet_names" :key="sheet" :value="sheet">{{ sheet }}</option></select></label></div>
            <div class="analytics-mapping-heading"><div><h3>字段映射</h3><p>告诉系统哪一列代表学生，哪些列用于统计。未知字段会保留在原始文件中。</p></div>
              <select @change="applyMappingTemplate"><option value="">选择映射模板</option><option v-for="item in mappings" :key="item.id" :value="item.id">{{ item.title }}{{ item.builtin ? '（内置）' : '' }}</option></select></div>
            <div v-if="mapping" class="analytics-mapping-grid">
              <label>学生标识列<select v-model="mapping.student_code"><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
              <label>学生姓名列<select v-model="mapping.student_name"><option :value="null">不使用</option><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
              <label>日期/时间列<select v-model="mapping.occurred_at"><option :value="null">不使用</option><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
              <label>活动/测验名称列<select v-model="mapping.activity"><option :value="null">不使用</option><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
              <label>章节/知识点列<select v-model="mapping.knowledge_tag"><option :value="null">不使用</option><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
              <label>每行满分列（可选）<select v-model="mapping.maximum_column"><option :value="null">使用指标固定满分</option><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
            </div>
            <div class="analytics-metric-list"><div class="section-heading"><div><h3>分析指标 <span class="muted">{{ mapping?.metrics?.length || 0 }}/12</span></h3><p>状态文本会尝试转成完成/出勤率；不认识的文本保留为类别统计。</p></div>
                <button class="button secondary" :disabled="mapping?.metrics?.length >= 12" @click="addMetric"><Plus :size="15" />添加指标</button></div>
              <div v-for="(metric, index) in mapping?.metrics || []" :key="index" class="analytics-metric-row">
                <label>数据列<select v-model="metric.column"><option v-for="column in draft.columns" :key="column" :value="column">{{ column }}</option></select></label>
                <label>指标名称<input v-model="metric.label" maxlength="120" placeholder="如：期中成绩"></label>
                <label>统计类型<select v-model="metric.kind"><option value="score">成绩</option><option value="homework">作业完成</option><option value="attendance">考勤</option><option value="number">数值</option><option value="category">分类</option></select></label>
                <label v-if="metric.kind === 'score'">满分<input v-model.number="metric.maximum" type="number" min="0" step="1" placeholder="未知"></label>
                <button class="button subtle icon-only danger-text" :disabled="mapping.metrics.length <= 1" aria-label="移除指标" @click="mapping.metrics.splice(index, 1)"><Trash2 :size="15" /></button>
              </div>
            </div>
            <div class="analytics-mapping-actions"><button class="button secondary" :disabled="busy" @click="saveMapping"><Check :size="15" />保存映射并预览</button>
              <button class="button subtle" :disabled="!draft.valid_count" @click="saveMappingTemplate"><Layers3 :size="15" />保存为映射模板</button>
              <button class="button primary" :disabled="busy || !draft.valid_count || !draft.mapping?.metrics?.length" @click="confirmImport"><ArrowDownToLine :size="15" />确认导入</button></div>
            <div v-if="draft.mapping?.metrics?.length" class="analytics-validation"><span><Check :size="15" />有效 {{ draft.valid_count }} 行</span><span><AlertCircle :size="15" />需复核 {{ draft.invalid_count }} 行</span></div>
            <div v-if="previewIssues.length" class="analytics-issues"><h3>待复核行（最多显示 50 条）</h3><div v-for="issue in previewIssues" :key="`${issue.row}-${issue.reason}`"><strong>第 {{ issue.row }} 行</strong>{{ issue.reason }}</div></div>
            <div v-if="draft.sample_rows?.length" class="analytics-sample"><div class="section-heading"><h3>前 {{ draft.sample_rows.length }} 行预览</h3><span class="muted">{{ draft.sheet_name || 'CSV 内容' }}</span></div>
              <div class="table-scroll"><table class="data-table"><thead><tr><th v-for="column in draft.columns" :key="column">{{ column }}</th></tr></thead><tbody><tr v-for="(row, index) in draft.sample_rows" :key="index"><td v-for="column in draft.columns" :key="column">{{ row[column] ?? '—' }}</td></tr></tbody></table></div></div>
          </template>
        </article>
        <aside class="panel analytics-import-aside"><div class="section-heading"><div><h2>导入批次</h2><p>私有数据按当前教师隔离。</p></div><span class="status-tag">{{ imports.length }}</span></div>
          <article v-for="item in imports" :key="item.id" class="analytics-import-row" :class="{ current: draft?.id === item.id }">
            <button class="analytics-import-open" @click="draft = item; mapping = item.mapping && Object.keys(item.mapping).length ? structuredClone(item.mapping) : null; previewIssues = []; changeView('imports')">
              <strong>{{ item.title }}</strong><small>{{ item.original_filename }}</small><span class="status-tag" :class="item.status">{{ statusNames[item.status] || item.status }}</span>
              <small v-if="item.status === 'processing'">已写入 {{ item.processed_count }} 条指标</small><small v-else>{{ item.valid_count || item.row_count }} 条记录 · {{ item.term_label || '未标学期' }}</small>
              <small v-if="item.error" class="danger-text">{{ item.error }}</small>
            </button>
            <div class="actions"><button v-if="item.status === 'failed'" class="button subtle" @click="retryImport(item)">重试</button><button v-if="!['queued','processing'].includes(item.status)" class="button subtle icon-only danger-text" :aria-label="`删除${item.title}`" @click="removeImport(item)"><Trash2 :size="14" /></button></div>
          </article><div v-if="!imports.length" class="analytics-side-empty">尚无导入数据。先选择表格文件并确认字段映射。</div>
          <div class="analytics-worker-hint"><Clock3 :size="15" /><span>确认导入后，需由后台分析 worker 处理。若批次一直排队，请按项目运行说明启动 worker。</span></div>
        </aside>
      </section>
    </template>

    <template v-else>
      <section class="analytics-plan-layout">
        <article class="panel analytics-plan-builder"><div class="section-heading"><div><h2><Sparkles :size="19" />生成计划草稿</h2><p>AI 仅接收聚合指标，不发送姓名、学号或原始行数据。</p></div><span class="status-tag">教师审核</span></div>
          <div class="analytics-plan-controls"><label>计划范围<select v-model="planScope"><option value="class">班级教学计划</option><option value="student">单个学生学习计划</option></select></label>
            <label v-if="planScope === 'student'">选择学生<select v-model="planStudent"><option value="">请选择学生</option><option v-for="item in students" :key="item.student_code" :value="item.student_code">{{ item.student_name || '未提供姓名' }} · {{ item.student_code }}</option></select></label>
            <label>关注重点（可选）<textarea v-model="planFocus" rows="3" maxlength="1000" placeholder="例如：复核函数调用部分的作业完成情况，并安排一次课堂练习"></textarea></label>
          </div>
          <div class="analytics-resource-select"><div class="section-heading"><div><h3>推荐已发布的学习资源</h3><p>仅从当前已发布到共享池的内容中选择；资源缺少时不会编造链接。</p></div></div>
            <label class="analytics-search"><Search :size="16" /><input v-model="resourceQuery" placeholder="搜索题库、课件、导图或课程"></label>
            <div class="analytics-shared-list"><label v-for="item in filteredShared.slice(0, 12)" :key="item.id" class="analytics-shared-option"><input v-model="selectedResources" type="checkbox" :value="item.id"><span><strong>{{ item.title }}</strong><small>{{ { presentation: '演示文稿', mind_map: '思维导图', digital_course: '数字课程', question_bank: '在线题库' }[item.source_type] }} · {{ item.subject || '未标学科' }} · {{ item.section || '未标章节' }}</small></span></label>
              <div v-if="!filteredShared.length" class="analytics-side-empty">共享池当前没有匹配内容。教师可以先在下方发布课件、题库、导图或数字课程。</div></div>
          </div>
          <button class="button primary analytics-plan-button" :disabled="busy || !canGeneratePlan" @click="createPlan"><LoaderCircle v-if="busy" class="spin" :size="16" /><Sparkles v-else :size="16" />生成可编辑草稿</button>
        </article>
        <article class="panel analytics-plan-list"><div class="section-heading"><div><h2>已保存计划</h2><p>当前课程的教师草稿</p></div></div>
          <button v-for="item in plans" :key="item.id" class="analytics-plan-row" :class="{ active: activePlan?.id === item.id }" @click="selectPlan(item)"><span class="analytics-plan-icon"><Sparkles :size="16" /></span><span><strong>{{ item.title }}</strong><small>{{ item.scope === 'student' ? '个人学习计划' : '班级教学计划' }} · {{ formatDate(item.updated_at) }}</small></span><ChevronRight :size="15" /></button>
          <div v-if="!plans.length" class="analytics-side-empty">生成后的计划会保存在这里。</div></article>
      </section>
      <section v-if="activePlan" class="panel analytics-plan-editor"><header class="section-heading"><div><h2>编辑计划草稿</h2><p>可以自行修改计划正文与建议资源，再保存到教师工作台。</p></div><div class="actions"><span class="status-tag">{{ activePlan.generation_source === 'ai' ? 'AI 草稿' : '规则草稿' }}</span><button class="button subtle icon-only danger-text" aria-label="删除计划" @click="removePlan(activePlan)"><Trash2 :size="16" /></button></div></header>
        <div class="analytics-plan-fields"><label>计划名称<input v-model="activePlan.title" maxlength="160"></label><label>教师关注点<input v-model="activePlan.focus" maxlength="1000"></label><label>计划正文<textarea v-model="activePlan.content" rows="14" maxlength="20000"></textarea></label></div>
        <div v-if="activePlan.resource_ids?.length" class="analytics-plan-recommendations"><strong>关联资源</strong><span v-for="id in activePlan.resource_ids" :key="id">{{ shared.find((item) => item.id === id)?.title || '资源已下架' }}</span></div>
        <div class="actions analytics-plan-save"><button class="button primary" :disabled="busy" @click="savePlan"><Check :size="15" />保存计划</button></div></section>
      <section class="panel analytics-publish"><div class="section-heading"><div><h2><BookOpenCheck :size="19" />发布到平台共享池</h2><p>学生资源池入口后续由独立学生端接入；此处发布会记录教师、时间与资源版本。</p></div></div>
        <div class="analytics-publish-grid"><label>选择当前课程的内容<select v-model="publishSource" @change="fillPublishMeta(publishables.find((item) => `${item.source_type}:${item.id}` === publishSource))"><option value="">选择可发布内容</option><option v-for="item in publishables" :key="`${item.source_type}:${item.id}`" :value="`${item.source_type}:${item.id}`" :disabled="item.ready === false">{{ item.title }} · {{ { presentation: '演示文稿', mind_map: '思维导图', digital_course: '数字课程', question_bank: '在线题库' }[item.source_type] }}{{ item.ready === false ? '（尚未完成发布/视频）' : '' }}</option></select></label>
          <label>资源标题<input v-model="publishMeta.title" maxlength="160" placeholder="学生资源池中显示的标题"></label><label>摘要<input v-model="publishMeta.summary" maxlength="1200" placeholder="说明资源内容和适用方式"></label>
          <label>学科/课程<input v-model="publishMeta.subject" maxlength="100"></label><label>适用学段/专业<input v-model="publishMeta.academic_level" maxlength="80" placeholder="如：本科一年级"></label><label>学期<input v-model="publishMeta.term_label" maxlength="64"></label>
          <label>章节/主题<input v-model="publishMeta.section" maxlength="160"></label><label>关键词<input v-model="publishMeta.keywords" placeholder="用逗号分隔关键词"></label></div>
        <button class="button primary" :disabled="busy || !publishSource || !publishMeta.title.trim()" @click="publishResource"><Upload :size="15" />发布资源</button>
        <div class="analytics-published-list"><div class="section-heading"><h3>当前共享资源池</h3><label class="analytics-search"><Search :size="15" /><input v-model="resourceQuery" placeholder="按名称、章节或关键词搜索"></label></div>
          <article v-for="item in filteredShared" :key="item.id" class="analytics-published-row"><span class="analytics-resource-type">{{ { presentation: 'PPT', mind_map: '导图', digital_course: '课程', question_bank: '题库' }[item.source_type] }}</span><div><strong>{{ item.title }}</strong><small>{{ item.subject || '未标学科' }} · {{ item.section || '未标章节' }} · {{ item.term_label || '未标学期' }}</small><small>{{ item.owner_name || `发布于 ${formatDate(item.published_at)}` }} · v{{ item.version }}</small></div><button v-if="item.owner_id === context.owner_id" class="button subtle" @click="withdrawResource(item)">下架</button></article>
          <div v-if="!filteredShared.length" class="analytics-side-empty">尚无已发布资源。</div></div>
      </section>
    </template>

    <input ref="fileInput" class="sr-only" type="file" accept=".csv,.xls,.xlsx" @change="uploadFile">

    <div v-if="studentPanel" class="analytics-student-backdrop" @click.self="closeStudentPanel">
    <section class="analytics-student-dialog panel" role="dialog" aria-modal="true" aria-labelledby="student-detail-title">
      <header class="dialog-header"><div><h2 id="student-detail-title">{{ studentPanel?.student_name || '学生记录' }}</h2><p>{{ studentPanel?.student_code }} · 最多展示 500 条指标记录</p></div><button class="button subtle icon-only" aria-label="关闭" @click="closeStudentPanel"><X :size="18" /></button></header>
      <div v-if="studentPanel" class="analytics-student-detail"><div class="analytics-student-warning"><AlertCircle :size="16" />这里只展示导入记录，未进行能力诊断或排名。计划生成时不向模型发送姓名和学号。</div>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>指标</th><th>数值</th><th>知识点/活动</th><th>时间</th></tr></thead><tbody><tr v-for="(item, index) in studentPanel.entries" :key="`${item.batch_id}-${item.source_row}-${index}`"><td>{{ item.metric_label }}</td><td>{{ item.value_number ?? item.value_text }}</td><td>{{ item.knowledge_tag || item.activity || '—' }}</td><td>{{ item.occurred_at ? formatDate(item.occurred_at) : '—' }}</td></tr></tbody></table></div>
        <button class="button primary" @click="prepareStudentPlan"><Sparkles :size="15" />生成个人学习计划草稿</button></div>
    </section></div>
  </div>
</template>

<style scoped>
.analytics-page { max-width: 1580px; }
.analytics-heading { display:flex; justify-content:space-between; align-items:flex-end; gap:20px; flex-wrap:wrap; margin-bottom:22px; }
.analytics-heading p { color:var(--muted); margin-top:8px; max-width:760px; }
.eyebrow { display:flex; align-items:center; gap:7px; color:var(--accent); font-size:12px; font-weight:650; letter-spacing:.06em; margin-bottom:8px; }
.analytics-tabs { margin-bottom:17px; }
.analytics-tabs button { padding:8px 13px; }
.analytics-tabs button[aria-pressed="true"] { background:var(--hover); color:var(--text); }
.analytics-loading { display:flex; align-items:center; justify-content:center; gap:10px; padding:64px; color:var(--muted); }
.analytics-filters { display:flex; align-items:flex-end; gap:14px; flex-wrap:wrap; padding:15px; margin-bottom:14px; }
.analytics-filters > div { display:grid; gap:7px; }
.analytics-filters label { min-width:205px; }
.analytics-layout-tools { display:flex; align-items:center; gap:14px; flex-wrap:wrap; padding:12px 15px; margin-bottom:14px; }
.analytics-layout-tools > label { min-width:190px; display:grid; gap:5px; color:var(--muted); font-size:11px; }
.analytics-panel-toggles { display:flex; align-items:center; gap:11px; flex-wrap:wrap; flex:1; color:var(--muted); font-size:11px; }
.analytics-panel-toggles label { display:flex; align-items:center; gap:5px; white-space:nowrap; }
.analytics-panel-toggles input { accent-color:var(--accent); }
.analytics-source-line { display:flex; align-items:center; gap:10px; flex-wrap:wrap; color:var(--muted); font-size:12px; margin:2px 2px 12px; }
.analytics-source-line .status-tag { display:flex; align-items:center; gap:4px; }
.analytics-source-line .button { margin-left:auto; }
.analytics-kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-bottom:13px; }
.analytics-kpis article { display:grid; gap:5px; padding:16px 18px; }
.analytics-kpis article > span { color:var(--muted); font-size:12px; }
.analytics-kpis strong { font-size:28px; font-weight:680; font-variant-numeric:tabular-nums; }
.analytics-kpis small { color:var(--muted); font-size:11px; }
.analytics-chart-grid { display:grid; grid-template-columns:1.35fr 1fr; gap:13px; margin-bottom:13px; }
.analytics-chart-card { min-width:0; padding:16px; }
.analytics-chart-card .section-heading { align-items:flex-start; }
.analytics-chart-card h2 { font-size:15px; }
.analytics-chart-card p,.analytics-students header p,.analytics-import-main .section-heading p,.analytics-publish .section-heading p { color:var(--muted); font-size:12px; margin-top:4px; }
.analytics-chart { width:100%; height:255px; margin-top:5px; }
.analytics-chart.short { height:224px; }
.analytics-note-card { display:flex; align-items:center; gap:13px; padding:18px; }
.analytics-note-card h2 { font-size:15px; margin-bottom:6px; }
.analytics-note-card p { color:var(--muted); font-size:12px; }
.analytics-note-card p + p { margin-top:6px; }
.note-icon,.analytics-plan-icon { display:grid; place-items:center; width:38px; height:38px; flex:none; border-radius:12px; color:var(--accent); background:var(--raised); }
.analytics-students { padding:17px; margin-bottom:17px; }
.analytics-students header { margin-bottom:13px; }
.analytics-students .data-table td:last-child { text-align:right; }
.analytics-student-link { display:grid; text-align:left; border:0; background:transparent; padding:0; }
.analytics-student-link:hover strong { color:var(--accent); }
.analytics-student-link small { color:var(--muted); font-size:11px; }
.analytics-empty-row { color:var(--muted); text-align:center!important; padding:30px!important; }
.analytics-empty { display:grid; justify-items:center; text-align:center; padding:48px 20px; gap:13px; }
.analytics-empty p { color:var(--muted); max-width:560px; }
.empty-art { display:grid; place-items:center; width:58px; height:58px; border-radius:18px; background:var(--raised); color:var(--accent); }
.analytics-empty-files { display:flex; align-items:center; gap:12px; flex-wrap:wrap; color:var(--muted); font-size:12px; margin-top:5px; }
.analytics-empty-files a { color:var(--accent); }
.analytics-import-layout { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(260px,.8fr); align-items:start; gap:14px; }
.analytics-import-main,.analytics-import-aside { padding:17px; min-width:0; }
.analytics-import-main > .section-heading { margin-bottom:13px; }
.analytics-upload-strip { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:12px; border:1px dashed var(--line); border-radius:11px; color:var(--muted); font-size:12px; margin-bottom:15px; }
.analytics-upload-strip svg { color:var(--accent); flex:none; }
.analytics-upload-strip .analytics-empty-files { margin-left:auto; margin-top:0; }
.analytics-draft-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; border-top:1px solid var(--line); border-bottom:1px solid var(--line); padding:12px 0; }
.analytics-draft-heading > div { display:grid; grid-template-columns:auto 1fr; align-items:center; column-gap:9px; row-gap:2px; min-width:0; }
.analytics-draft-heading strong { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analytics-draft-heading small { grid-column:2; color:var(--muted); font-size:11px; }
.analytics-draft-meta,.analytics-mapping-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; padding-block:14px; }
.analytics-mapping-heading { display:flex; justify-content:space-between; gap:12px; align-items:flex-end; margin-top:4px; }
.analytics-mapping-heading p,.analytics-metric-list .section-heading p { color:var(--muted); font-size:12px; margin-top:4px; }
.analytics-mapping-heading select { max-width:230px; }
.analytics-metric-list { display:grid; gap:8px; margin:9px 0 13px; }
.analytics-metric-row { display:grid; grid-template-columns:minmax(130px,1fr) minmax(120px,1fr) minmax(130px,.9fr) 90px auto; gap:8px; align-items:end; padding:9px; border:1px solid var(--line); border-radius:11px; background:var(--bg); }
.analytics-metric-row label { font-size:11px; color:var(--muted); }
.analytics-metric-row .icon-only { margin-bottom:1px; }
.analytics-mapping-actions { display:flex; justify-content:flex-end; gap:8px; flex-wrap:wrap; }
.analytics-validation { display:flex; gap:15px; color:var(--muted); font-size:12px; padding:10px 2px; }
.analytics-validation span { display:flex; align-items:center; gap:5px; }
.analytics-validation span:first-child svg { color:var(--success); }
.analytics-validation span:last-child svg { color:#e8ac61; }
.analytics-issues { max-height:170px; overflow:auto; padding:10px; border:1px solid var(--line); border-radius:10px; background:var(--bg); }
.analytics-issues h3 { margin-bottom:6px; }
.analytics-issues > div { display:flex; gap:10px; padding:4px 0; color:var(--muted); font-size:12px; }
.analytics-issues strong { color:var(--text); }
.analytics-sample { margin-top:14px; }
.analytics-sample .section-heading { margin-bottom:7px; }
.analytics-sample .table-scroll { max-height:240px; overflow:auto; }
.analytics-sample .data-table { min-width:620px; font-size:12px; }
.analytics-sample .data-table th,.analytics-sample .data-table td { padding:7px 9px; }
.analytics-import-aside { position:sticky; top:80px; }
.analytics-import-aside > .section-heading { margin-bottom:9px; }
.analytics-import-row { position:relative; border-top:1px solid var(--line); padding:9px 0; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px; }
.analytics-import-row.current { background:var(--raised); margin-inline:-8px; padding-inline:8px; border-radius:9px; }
.analytics-import-open { display:grid; min-width:0; gap:4px; text-align:left; border:0; background:transparent; }
.analytics-import-open strong,.analytics-import-open small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analytics-import-open small { color:var(--muted); font-size:11px; }
.analytics-import-open .status-tag { width:max-content; }
.analytics-import-row .actions { align-self:center; }
.status-tag.queued,.status-tag.processing { color:#d4a853; }
.status-tag.failed { color:var(--danger); }
.analytics-worker-hint { display:flex; gap:8px; border-top:1px solid var(--line); padding-top:12px; margin-top:6px; color:var(--muted); font-size:11px; }
.analytics-worker-hint svg { flex:none; color:#dda95e; }
.analytics-side-empty { color:var(--muted); font-size:12px; padding:15px 5px; text-align:center; }
.analytics-plan-layout { display:grid; grid-template-columns:minmax(0,1.25fr) minmax(260px,.75fr); gap:14px; align-items:start; }
.analytics-plan-builder,.analytics-plan-list,.analytics-plan-editor,.analytics-publish { padding:17px; min-width:0; }
.analytics-plan-builder > .section-heading,.analytics-plan-list > .section-heading { margin-bottom:14px; }
.analytics-plan-builder > .section-heading p,.analytics-plan-list > .section-heading p { color:var(--muted); font-size:12px; margin-top:4px; }
.analytics-plan-controls { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.analytics-plan-controls label:last-child { grid-column:1/-1; }
.analytics-resource-select { border-top:1px solid var(--line); margin-top:14px; padding-top:13px; }
.analytics-resource-select .section-heading { margin-bottom:9px; }
.analytics-resource-select .section-heading p { color:var(--muted); font-size:11px; margin-top:4px; }
.analytics-search { display:flex; align-items:center; gap:7px; background:var(--bg); border:1px solid var(--line); border-radius:9px; padding:0 9px; }
.analytics-search svg { color:var(--muted); flex:none; }
.analytics-search input { flex:1; border:0!important; background:transparent!important; padding-inline:0!important; }
.analytics-shared-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:6px; max-height:210px; overflow:auto; margin-top:8px; }
.analytics-shared-option { display:flex; align-items:flex-start; gap:8px; padding:8px; border:1px solid var(--line); border-radius:9px; cursor:pointer; }
.analytics-shared-option input { margin-top:4px; accent-color:var(--accent); }
.analytics-shared-option span { display:grid; min-width:0; }
.analytics-shared-option strong,.analytics-shared-option small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analytics-shared-option small { color:var(--muted); font-size:10px; }
.analytics-plan-button { margin-top:15px; }
.analytics-plan-list { position:sticky; top:80px; }
.analytics-plan-row { width:100%; display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:10px; text-align:left; background:transparent; color:inherit; border:0; border-top:1px solid var(--line); padding:10px 3px; }
.analytics-plan-row.active,.analytics-plan-row:hover { background:var(--raised); }
.analytics-plan-row > span:nth-child(2) { display:grid; min-width:0; }
.analytics-plan-row strong,.analytics-plan-row small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analytics-plan-row small { color:var(--muted); font-size:11px; }
.analytics-plan-editor,.analytics-publish { margin-top:14px; }
.analytics-plan-fields { display:grid; gap:11px; margin-top:12px; }
.analytics-plan-fields textarea { line-height:1.7; }
.analytics-plan-save { justify-content:flex-end; margin-top:11px; }
.analytics-plan-recommendations { display:flex; align-items:center; flex-wrap:wrap; gap:8px; color:var(--muted); font-size:11px; }
.analytics-plan-recommendations span { padding:4px 8px; border-radius:7px; background:var(--raised); color:var(--text); }
.analytics-publish-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:11px; margin:13px 0; }
.analytics-published-list { border-top:1px solid var(--line); margin-top:15px; padding-top:12px; }
.analytics-published-list > .section-heading { margin-bottom:5px; }
.analytics-published-list .analytics-search { width:min(300px,100%); }
.analytics-published-row { display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:10px; align-items:center; padding:9px 0; border-top:1px solid var(--line); }
.analytics-published-row > div { display:grid; min-width:0; }
.analytics-published-row strong,.analytics-published-row small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.analytics-published-row small { color:var(--muted); font-size:10px; }
.analytics-resource-type { display:grid; place-items:center; width:38px; height:34px; border-radius:9px; background:var(--raised); color:var(--accent); font-size:10px; font-weight:650; }
.analytics-student-backdrop { position:fixed; z-index:20; inset:0; display:grid; place-items:center; padding:12px; background:#080713b0; backdrop-filter:blur(3px); }
.analytics-student-dialog { display:block; width:min(940px,calc(100% - 24px)); max-height:calc(100vh - 24px); overflow:hidden; }
.analytics-student-dialog > .dialog-header p { color:var(--muted); margin-top:3px; font-size:12px; }
.analytics-student-detail { padding:15px; display:grid; gap:13px; }
.analytics-student-detail .table-scroll { max-height:min(55vh,560px); overflow:auto; }
.analytics-student-detail .data-table { min-width:650px; }
.analytics-student-warning { display:flex; align-items:center; gap:8px; padding:9px 11px; background:var(--raised); border-radius:9px; color:var(--muted); font-size:11px; }
.analytics-student-warning svg { flex:none; color:#dda95e; }
.spin { animation:analytics-spin 1s linear infinite; }
@keyframes analytics-spin { to { transform:rotate(360deg); } }
@media(max-width:1050px) { .analytics-import-layout,.analytics-plan-layout { grid-template-columns:1fr; } .analytics-import-aside,.analytics-plan-list { position:static; } .analytics-kpis { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:760px) { .analytics-chart-grid { grid-template-columns:1fr; } .analytics-draft-meta,.analytics-mapping-grid,.analytics-plan-controls,.analytics-publish-grid { grid-template-columns:1fr; } .analytics-mapping-heading { align-items:flex-start; flex-direction:column; } .analytics-metric-row { grid-template-columns:repeat(2,minmax(0,1fr)); } .analytics-metric-row .icon-only { justify-self:end; } .analytics-shared-list { grid-template-columns:1fr; } .analytics-source-line .button { margin-left:0; } }
</style>
