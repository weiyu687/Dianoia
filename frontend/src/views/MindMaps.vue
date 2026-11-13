<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowRight, Copy, FilePlus2, LayoutTemplate, Pencil, Plus, Search, Sparkles, Trash2, Workflow } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { api, formatDate } from '../api'
import { course, courseId } from '../session'
import Empty from '../components/Empty.vue'
import MapSources from '../components/MapSources.vue'
import MindMapPreview from '../components/MindMapPreview.vue'
import Modal from '../components/Modal.vue'
import '../mindMaps.css'

const route = useRoute()
const router = useRouter()
const maps = ref([])
const templates = ref({ builtin: [], personal: [] })
const resources = ref([])
const tab = ref(route.query.tab === 'templates' ? 'templates' : 'maps')
const filter = ref('')
const query = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const dialog = ref(null)
const matches = (row) => row.title.toLowerCase().includes(query.value.trim().toLowerCase())
const visibleMaps = computed(() => maps.value.filter(matches))
const builtin = computed(() => templates.value.builtin.filter((row) => matches(row) && (!filter.value || filter.value === row.category)))
const categories = computed(() => [...new Set(templates.value.builtin.map((item) => item.category))])
const personal = computed(() => templates.value.personal.filter(matches))

onMounted(async () => {
  try {
    const [items, designs, files] = await Promise.all([
      api(`/mind-maps?course_id=${courseId.value}`), api('/mind-map-templates'), api(`/resources?course_id=${courseId.value}`),
    ])
    maps.value = items
    templates.value = designs
    resources.value = files.filter((file) => file.status === 'ready' && file.page_count)
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function showTab(value) {
  tab.value = value
  query.value = ''
  filter.value = ''
  router.replace({ query: value === 'templates' ? { tab: 'templates' } : {} })
}

function open(mode, item = null, kind = 'map') {
  formError.value = ''
  dialog.value = { mode, kind, item, title: item?.title || '', template: mode === 'use' ? item.id : '', instruction: '', sources: [] }
}

function close() {
  if (!busy.value) dialog.value = null
}

async function copy(item) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api(`/mind-maps/${item.id}/copy`, {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() },
    })
    maps.value = [result, ...maps.value.filter((row) => row.id !== result.id)]
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

async function submit() {
  if (busy.value) return
  busy.value = true
  formError.value = ''
  const { mode, kind, item, title, template, instruction, sources } = dialog.value
  const path = kind === 'template' ? '/mind-map-templates' : '/mind-maps'
  try {
    if (mode === 'rename' || mode === 'delete') {
      const deleting = mode === 'delete'
      const result = await api(`${path}/${item.id}`, {
        method: deleting ? 'DELETE' : 'PUT', body: deleting ? undefined : { title, revision: item.revision },
      })
      const rows = kind === 'template' ? templates.value.personal : maps.value
      const updated = rows.flatMap((row) => row.id !== item.id ? [row] : result ? [result] : [])
      if (kind === 'template') templates.value.personal = updated
      else maps.value = updated
    } else {
      const body = kind === 'template' ? { title } : {
        course_id: courseId.value, title, template_id: template || null, instruction, sources,
      }
      const result = await api(mode === 'ai' ? `${path}/generate` : path, { method: 'POST', body })
      await router.push(`${path}/${result.id}`)
    }
    dialog.value = null
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}

const dialogTitle = computed(() => ({
  ai: 'AI 生成思维导图', blank: '空白新建', use: '使用模板', template: '制作新模板', rename: '重命名', delete: '确认删除',
})[dialog.value?.mode])
</script>

<template>
  <div class="page mind-hub">
    <header class="page-heading">
      <div><h1>思维导图</h1><p>{{ course.name }}</p></div>
      <div class="actions">
        <button v-if="tab === 'templates'" class="button secondary" :disabled="busy" @click="open('template', null, 'template')"><FilePlus2 :size="17" /> 制作模板</button>
        <button v-else class="button secondary" :disabled="busy" @click="open('blank')"><Plus :size="18" /> 空白新建</button>
        <button class="button primary" :disabled="busy" @click="open('ai')"><Sparkles :size="17" /> AI 生成</button>
      </div>
    </header>
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <div class="list-tools">
      <div class="segmented" aria-label="导图工作区">
        <button :aria-pressed="tab === 'maps'" @click="showTab('maps')"><Workflow :size="16" /> 我的导图</button>
        <button :aria-pressed="tab === 'templates'" @click="showTab('templates')"><LayoutTemplate :size="16" /> 模板库</button>
      </div>
      <label class="search"><Search :size="17" /><input v-model="query" type="search" aria-label="搜索导图或模板" :placeholder="tab === 'maps' ? '搜索导图' : '搜索模板'"></label>
    </div>
    <div v-if="loading" class="empty-state" role="status">正在加载</div>
    <template v-else-if="tab === 'maps'">
      <div v-if="visibleMaps.length" class="table-scroll">
        <table class="data-table">
          <thead><tr><th>导图名称</th><th>版本</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody><tr v-for="row in visibleMaps" :key="row.id">
            <td><RouterLink class="file-title" :to="`/mind-maps/${row.id}`"><span class="file-icon lesson-icon"><Workflow :size="18" /></span><strong>{{ row.title }}</strong></RouterLink></td>
            <td>v{{ row.revision }}</td><td>{{ formatDate(row.updated_at) }}</td>
            <td><div class="actions map-row-actions">
              <button type="button" class="button subtle icon-only" aria-label="重命名导图" title="重命名" :disabled="busy" @click="open('rename', row)"><Pencil :size="16" /></button>
              <button type="button" class="button subtle icon-only" aria-label="复制导图" title="复制" :disabled="busy" @click="copy(row)"><Copy :size="16" /></button>
              <button type="button" class="button subtle icon-only" aria-label="删除导图" title="删除" :disabled="busy" @click="open('delete', row)"><Trash2 :size="16" /></button>
            </div></td>
          </tr></tbody>
        </table>
      </div>
      <Empty v-else :title="query ? '没有找到匹配的导图' : '还没有思维导图'" :detail="query ? '' : '可从空白、教学模板或 AI 生成开始。'">
        <button v-if="!query" class="button secondary" @click="showTab('templates')">浏览模板 <ArrowRight :size="16" /></button>
      </Empty>
    </template>
    <template v-else>
      <section class="map-gallery-section" aria-label="内置模板">
        <header class="section-heading"><h2>内置模板</h2>
          <div class="map-category">
            <button class="button subtle" :aria-pressed="!filter" @click="filter = ''">全部</button>
            <button v-for="category in categories" :key="category" class="button subtle" :aria-pressed="filter === category" @click="filter = category">{{ category }}</button>
          </div>
        </header>
        <div v-if="builtin.length" class="map-gallery">
          <button v-for="item in builtin" :key="item.id" type="button" class="map-template-card" @click="open('use', item)">
            <MindMapPreview :document="item.document" />
            <span class="map-card-copy"><strong>{{ item.title }}</strong><small>{{ item.description }}</small></span>
          </button>
        </div>
        <p v-else class="muted">没有找到匹配的模板。</p>
      </section>
      <section class="map-gallery-section" aria-label="我的模板">
        <header class="section-heading"><h2>我的模板</h2></header>
        <div v-if="personal.length" class="map-gallery">
          <article v-for="item in personal" :key="`${item.id}:${item.revision}`" class="map-template-card">
            <button type="button" class="map-card-apply" :aria-label="`使用模板 ${item.title}`" @click="open('use', item)"><MindMapPreview :document="item.document" /></button>
            <div class="map-card-copy"><strong>{{ item.title }}</strong><small>{{ formatDate(item.updated_at) }}</small></div>
            <div class="actions map-personal-actions">
              <button class="button secondary" type="button" @click="open('use', item)">使用</button>
              <RouterLink class="button subtle" :to="`/mind-map-templates/${item.id}`">编辑</RouterLink>
              <button class="button subtle icon-only" type="button" title="重命名模板" aria-label="重命名模板" @click="open('rename', item, 'template')"><Pencil :size="15" /></button>
              <button class="button subtle icon-only" type="button" title="删除模板" aria-label="删除模板" @click="open('delete', item, 'template')"><Trash2 :size="15" /></button>
            </div>
          </article>
        </div>
        <Empty v-else title="没有找到个人模板" :detail="query ? '' : '可以从零制作，也可以把已有导图存为模板。'" />
      </section>
    </template>
    <Modal :open="!!dialog" :title="dialogTitle" :wide="['ai', 'use'].includes(dialog?.mode)" @close="close">
      <form v-if="dialog" class="stack" @submit.prevent="submit">
        <p v-if="dialog.mode === 'delete'">删除「{{ dialog.item.title }}」？</p>
        <template v-else>
          <MindMapPreview v-if="dialog.mode === 'use'" :document="dialog.item.document" />
          <label>{{ dialog.kind === 'template' ? '模板名称' : '导图名称' }}<input v-model.trim="dialog.title" required maxlength="160"></label>
          <template v-if="dialog.mode === 'ai'">
            <label>参考模板<select v-model="dialog.template"><option value="">自由组织</option><option v-for="item in [...templates.builtin, ...templates.personal]" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
            <label>生成要求<textarea v-model="dialog.instruction" maxlength="2000" rows="3" placeholder="例如：用于 Python 函数复习，按定义、参数和返回值组织"></textarea></label>
            <MapSources v-model="dialog.sources" :resources="resources" />
          </template>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions">
          <button class="button secondary" type="button" :disabled="busy" @click="close">取消</button>
          <button class="button" :class="dialog.mode === 'delete' ? 'danger' : 'primary'" type="submit" :disabled="busy">{{ busy ? '正在处理…' : ({ ai: '生成导图', use: '创建导图', blank: '创建导图', template: '创建模板', rename: '保存名称', delete: '删除' })[dialog.mode] }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
