<script setup>
import { computed, onMounted, ref } from 'vue'
import { Copy, LayoutTemplate, Plus, Presentation, Search, Sparkles, Trash2, Pencil } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, formatDate } from '../api'
import { course, courseId } from '../session'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'
import MapSources from '../components/MapSources.vue'
import SlideThumbnail from '../components/SlideThumbnail.vue'
import '../presentations.css'

const router = useRouter()
const rows = ref([])
const templates = ref([])
const resources = ref([])
const lessons = ref([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const formError = ref('')
const section = ref('decks')
const search = ref('')
const modal = ref(null)
const visible = computed(() => (section.value === 'decks' ? rows.value : templates.value)
  .filter((item) => item.title.toLowerCase().includes(search.value.trim().toLowerCase())))

onMounted(async () => {
  try {
    const id = courseId.value
    const [decks, styles, material, plans] = await Promise.all([
      api('/presentations?course_id=' + id), api('/presentation-templates'),
      api('/resources?course_id=' + id), api('/lessons?course_id=' + id),
    ])
    rows.value = decks
    templates.value = styles
    resources.value = material.filter((item) => item.status === 'ready')
    lessons.value = plans.filter((item) => item.status !== 'archived')
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function open(mode, template = null) {
  formError.value = ''
  modal.value = { mode, title: '', template_id: template?.id || '', page_count: 8, minutes: 45,
    audience: '本科生', lesson_id: '', instruction: '', sources: [], outline: [] }
}

async function submit() {
  if (busy.value) return
  const form = modal.value
  busy.value = true
  formError.value = ''
  try {
    if (form.mode === 'delete') {
      await api(form.url, { method: 'DELETE' })
      if (form.template) templates.value = templates.value.filter((item) => item.id !== form.item.id)
      else rows.value = rows.value.filter((item) => item.id !== form.item.id)
    } else if (form.mode === 'rename') {
      const updated = await api(form.url, { method: 'PATCH', body: { title: form.title } })
      templates.value = templates.value.map((item) => item.id === updated.id ? updated : item)
    } else {
      const body = { ...form, template_id: form.template_id || null, lesson_id: form.lesson_id || null, course_id: courseId.value }
      if (form.mode === 'AI' && !form.outline.length) {
        form.outline = await api('/presentations/outline', { method: 'POST', body })
        return
      }
      const result = await api(form.mode === 'AI' ? '/presentations/generate' : '/presentations', { method: 'POST', body })
      await router.push('/presentations/' + result.id)
    }
    modal.value = null
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}

async function copy(item) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api('/presentations/' + item.id + '/copy', { method: 'POST' })
    rows.value.unshift(result)
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

function movePage(index, delta) {
  const outline = modal.value.outline
  const next = index + delta
  if (next >= 0 && next < outline.length) [outline[index], outline[next]] = [outline[next], outline[index]]
}

function manage(mode, item, template = false) {
  formError.value = ''
  modal.value = { mode, item, template, title: item.title,
    url: (template ? '/presentation-templates/' : '/presentations/') + item.id }
}
</script>

<template>
  <div class="page presentation-home">
    <header class="page-heading">
      <div><h1>演示文稿</h1><p>{{ course.name }}</p></div>
      <div class="actions">
        <button class="button secondary" :disabled="loading || busy" @click="open('new')"><Plus :size="18" /> 新建课件</button>
        <button class="button primary" :disabled="loading || busy" @click="open('AI')"><Sparkles :size="18" /> AI 生成</button>
      </div>
    </header>
    <div class="section-heading presentation-filters">
      <div class="segmented">
        <button :aria-pressed="section === 'decks'" @click="section = 'decks'; search = ''"><Presentation :size="16" /> 我的课件</button>
        <button :aria-pressed="section === 'templates'" @click="section = 'templates'; search = ''"><LayoutTemplate :size="16" /> 模板库</button>
      </div>
      <label class="search"><Search :size="16" /><input v-model="search" aria-label="搜索" placeholder="搜索名称" type="search"></label>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading" class="empty-state" role="status">正在加载演示文稿</div>
    <template v-else-if="visible.length">
      <div v-if="section === 'decks'" class="table-scroll">
        <table class="data-table">
          <thead><tr><th>课件名称</th><th>版本</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody><tr v-for="item in visible" :key="item.id">
            <td><RouterLink class="file-title" :to="'/presentations/' + item.id"><span class="file-icon"><Presentation :size="18" /></span>{{ item.title }}</RouterLink></td>
            <td>v{{ item.revision }}</td><td>{{ formatDate(item.updated_at) }}</td>
            <td><div class="actions">
              <button class="button subtle icon-only" aria-label="复制课件" :disabled="busy" @click="copy(item)"><Copy :size="16" /></button>
              <button class="button subtle icon-only danger-text" aria-label="删除课件" :disabled="busy" @click="manage('delete', item)"><Trash2 :size="16" /></button>
            </div></td>
          </tr></tbody>
        </table>
      </div>
      <div v-else class="presentation-template-grid">
        <article v-for="item in visible" :key="item.id" class="panel presentation-template-card">
          <button type="button" class="presentation-template-select" :aria-label="'使用模板 ' + item.title" @click="open('new', item)">
            <span class="presentation-template-preview">
              <SlideThumbnail :slide="item.thumbnail" />
              <span v-if="item.sample" class="presentation-template-sample"><SlideThumbnail :slide="item.sample" /></span>
            </span>
            <span class="presentation-template-caption"><strong>{{ item.title }}</strong><small>{{ item.pages }} 页</small></span>
            <span v-if="item.headings?.length" class="presentation-template-headings">{{ item.headings.join(' · ') }}</span>
          </button>
          <div v-if="!item.builtin" class="actions">
            <button class="button subtle icon-only" aria-label="重命名模板" @click="manage('rename', item, true)"><Pencil :size="15" /></button>
            <button class="button subtle icon-only danger-text" aria-label="删除模板" @click="manage('delete', item, true)"><Trash2 :size="15" /></button>
          </div>
        </article>
      </div>
    </template>
    <Empty v-else :title="search ? '没有匹配的结果' : '还没有课件'" :detail="search ? '' : '新建空白课件，或从模板库选择教学版式。'" />
    <Modal :open="!!modal" :title="{ new: '新建课件', AI: 'AI 生成课件', rename: '重命名模板', delete: '删除确认' }[modal?.mode]"
      :wide="modal?.mode === 'AI'" @close="!busy && (modal = null)">
      <form v-if="modal" class="stack" @submit.prevent="submit">
        <p v-if="modal.mode === 'delete'">删除「{{ modal.item.title }}」？</p>
        <template v-else>
          <label>{{ modal.mode === 'rename' ? '模板名称' : '课件名称' }}<input v-model.trim="modal.title" maxlength="160" required></label>
          <label v-if="modal.mode !== 'rename'">模板<select v-model="modal.template_id">
            <option value="">{{ modal.mode === 'AI' ? '自动选择版式' : '空白' }}</option><option v-for="item in templates" :key="item.id" :value="item.id">{{ item.title }}</option>
          </select></label>
          <template v-if="modal.mode === 'AI'">
            <template v-if="!modal.outline.length">
              <label>授课对象<input v-model.trim="modal.audience" maxlength="160"></label>
              <div class="presentation-form-cols">
                <label>授课时间（分钟）<input v-model.number="modal.minutes" type="number" min="5" max="240" required></label>
                <label>页数<input v-model.number="modal.page_count" type="number" min="3" max="24" required></label>
              </div>
              <label>选用教案<select v-model="modal.lesson_id"><option value="">请选择</option><option v-for="item in lessons" :key="item.id" :value="item.id">{{ item.title }}</option></select></label>
              <label>生成要求<textarea v-model.trim="modal.instruction" rows="3" maxlength="2000"></textarea></label>
              <MapSources v-model="modal.sources" :resources="resources" />
            </template>
            <template v-else>
              <div class="section-heading"><h3>逐页大纲</h3><button type="button" class="button subtle" :disabled="busy" @click="modal.outline = []">返回生成设置</button></div>
              <div v-for="(page, index) in modal.outline" :key="index" class="panel presentation-outline">
                <label>第 {{ index + 1 }} 页<input v-model.trim="page.title" maxlength="160" required></label>
                <label>教学目的<textarea v-model.trim="page.purpose" rows="2" maxlength="500"></textarea></label>
                <div class="actions"><button type="button" class="button subtle" :disabled="!index || busy" @click="movePage(index, -1)">上移</button>
                  <button type="button" class="button subtle" :disabled="index === modal.outline.length - 1 || busy" @click="movePage(index, 1)">下移</button></div>
              </div>
            </template>
          </template>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions"><button class="button primary" type="submit" :disabled="busy">{{ busy ? '正在处理…' :
          modal.mode === 'AI' ? (modal.outline.length ? '生成课件' : '生成大纲') : modal.mode === 'delete' ? '删除' : modal.mode === 'rename' ? '保存' : '创建课件' }}</button></div>
      </form>
    </Modal>
  </div>
</template>
