<script setup>
import { computed, onMounted, ref } from 'vue'
import { ClipboardList, Copy, FileUp, LayoutTemplate, Pencil, Plus, Search, Sparkles, Trash2, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, formatDate } from '../api'
import { course, courseId } from '../session'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'
import MapSources from '../components/MapSources.vue'
import { examKinds } from '../examKinds'

const router = useRouter()
const items = ref([])
const templates = ref([])
const resources = ref([])
const classes = ref([])
const search = ref('')
const dialog = ref(null)
const error = ref('')
const formError = ref('')
const loading = ref(true)
const busy = ref(false)
const visible = computed(() => items.value.filter((item) => item.title.toLowerCase().includes(search.value.trim().toLowerCase())))
const total = computed(() => dialog.value?.groups.reduce((sum, group) => sum + group.count * group.points, 0) || 0)
const labels = { blank: '新建试卷', import: '导入 Word 原卷', ai: 'AI 组卷', rename: '重命名试卷', delete: '删除试卷' }

onMounted(async () => {
  try {
    const [rows, designs, files, groups] = await Promise.all([
      api(`/exams?course_id=${courseId.value}`), api('/exam-templates'), api(`/resources?course_id=${courseId.value}`),
      api(`/exams/course-fields?course_id=${courseId.value}`),
    ])
    items.value = rows
    templates.value = designs
    classes.value = groups
    resources.value = files.filter((file) => file.status === 'ready' && file.page_count
      && (!['doc', 'docx'].includes(file.extension) || file.has_preview))
  } catch (failure) { error.value = failure.message }
  finally { loading.value = false }
})

function open(mode, item = null) {
  formError.value = ''
  dialog.value = { mode, item, title: item?.title || '', file: null, template_id: '', class_code: classes.value.length === 1 ? classes.value[0].code : '', sources: [], instruction: '',
    difficulty: '适中', groups: [{ kind: 'single', count: 5, points: 2 }] }
}

function chooseFile(event) {
  const file = event.target.files[0]
  dialog.value.file = file || null
  if (file && !dialog.value.title) dialog.value.title = file.name.replace(/\.docx?$/i, '').slice(0, 160)
}

function addGroup() {
  const kind = Object.keys(examKinds).find((key) => !dialog.value.groups.some((group) => group.kind === key))
  if (kind) dialog.value.groups.push({ kind, count: 2, points: 5 })
}

async function submit() {
  if (busy.value) return
  busy.value = true
  formError.value = ''
  try {
    const { mode, item, title, file, template_id, class_code, sources, instruction, difficulty, groups } = dialog.value
    if (mode === 'rename') {
      const row = await api(`/exams/${item.id}`, { method: 'PATCH', body: { title } })
      items.value = [row, ...items.value.filter((entry) => entry.id !== row.id)]
    } else if (mode === 'delete') {
      await api(`/exams/${item.id}`, { method: 'DELETE' })
      items.value = items.value.filter((entry) => entry.id !== item.id)
    } else {
      let body = { course_id: courseId.value, title, template_id: template_id || null, class_code, sources }
      const endpoint = { import: '/exams/import', ai: '/exams/generate', blank: '/exams' }[mode]
      if (mode === 'import') {
        body = new FormData()
        body.append('file', file)
        body.append('title', title)
        body.append('course_id', courseId.value)
      } else if (mode === 'ai') Object.assign(body, { groups, instruction, difficulty })
      const row = await api(endpoint, { method: 'POST', body })
      await router.push(`/exams/${row.id}`)
    }
    dialog.value = null
  } catch (failure) { formError.value = failure.message }
  finally { busy.value = false }
}

async function copy(item) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try { items.value.unshift(await api(`/exams/${item.id}/copy`, { method: 'POST' })) }
  catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}
</script>

<template>
  <div class="page">
    <header class="page-heading">
      <div><h1>试卷管理</h1><p>{{ course.name }}</p></div>
      <div class="actions">
        <RouterLink class="button secondary" to="/exam-templates"><LayoutTemplate :size="17" /> Word 模板</RouterLink>
        <button class="button secondary" :disabled="busy" @click="open('import')"><FileUp :size="17" /> 导入原卷</button>
        <button class="button secondary" :disabled="busy" @click="open('blank')"><Plus :size="17" /> 新建试卷</button>
        <button class="button primary" :disabled="busy" @click="open('ai')"><Sparkles :size="17" /> AI 组卷</button>
      </div>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="list-tools"><label class="search"><Search :size="17" /><input v-model="search" type="search" aria-label="搜索试卷" placeholder="搜索试卷"></label></div>
    <div v-if="loading" class="empty-state" role="status">正在加载试卷</div>
    <div v-else-if="visible.length" class="table-scroll">
      <table class="data-table">
        <thead><tr><th>试卷名称</th><th>版本</th><th>更新时间</th><th><span class="sr-only">操作</span></th></tr></thead>
        <tbody><tr v-for="item in visible" :key="item.id">
          <td><RouterLink class="file-title" :to="`/exams/${item.id}`"><span class="file-icon lesson-icon"><ClipboardList :size="18" /></span><strong>{{ item.title }}</strong></RouterLink></td>
          <td>v{{ item.revision }}</td><td>{{ formatDate(item.updated_at) }}</td>
          <td><div class="actions template-actions">
            <button class="button subtle icon-only" type="button" aria-label="重命名试卷" :disabled="busy" @click="open('rename', item)"><Pencil :size="16" /></button>
            <button class="button subtle icon-only" type="button" aria-label="复制试卷" :disabled="busy" @click="copy(item)"><Copy :size="16" /></button>
            <button class="button subtle icon-only danger-text" type="button" aria-label="删除试卷" :disabled="busy" @click="open('delete', item)"><Trash2 :size="16" /></button>
          </div></td>
        </tr></tbody>
      </table>
    </div>
    <Empty v-else :title="search ? '没有找到匹配的试卷' : '还没有试卷'" :detail="search ? '' : '可导入已有 Word 原卷、套用模板或按要求组卷。'" />
    <Modal :open="!!dialog" :title="labels[dialog?.mode]" :wide="dialog?.mode === 'ai'" @close="!busy && (dialog = null)">
      <form v-if="dialog" class="stack" @submit.prevent="submit">
        <p v-if="dialog.mode === 'delete'">删除「{{ dialog.item.title }}」？</p>
        <template v-else>
          <label v-if="dialog.mode === 'import'">Word 原卷<input type="file" accept=".doc,.docx" required @change="chooseFile"></label>
          <label>试卷名称<input v-model.trim="dialog.title" maxlength="160" required></label>
          <label v-if="['blank', 'ai'].includes(dialog.mode)">Word 模板<select v-model="dialog.template_id">
            <option value="">默认版式</option>
            <option v-for="template in templates" :key="template.id" :value="template.id">{{ template.title }}</option>
          </select></label>
          <label v-if="['blank', 'ai'].includes(dialog.mode) && !dialog.template_id && classes.length">考试班级<select v-model="dialog.class_code">
            <option value="">留空，由教师填写</option><option v-for="group in classes" :key="group.code" :value="group.code">{{ group.name }}</option>
          </select></label>
          <template v-if="dialog.mode === 'ai'">
            <div class="section-heading"><strong>组卷明细 · {{ total }} 分</strong><button type="button" class="button secondary" :disabled="dialog.groups.length >= 5" @click="addGroup"><Plus :size="15" /> 添加题型</button></div>
            <div v-for="(group, index) in dialog.groups" :key="index" class="actions">
              <label>题型<select v-model="group.kind">
                <option v-for="(label, kind) in examKinds" :key="kind" :value="kind" :disabled="kind !== group.kind && dialog.groups.some((other) => other.kind === kind)">{{ label }}</option>
              </select></label>
              <label>题量<input v-model.number="group.count" type="number" min="1" max="20" required></label>
              <label>每题分值<input v-model.number="group.points" type="number" min="1" max="100" required></label>
              <button type="button" class="button subtle icon-only" aria-label="删除题型" :disabled="dialog.groups.length === 1" @click="dialog.groups.splice(index, 1)"><X :size="17" /></button>
            </div>
            <label>整体难度<select v-model="dialog.difficulty"><option>基础</option><option>适中</option><option>较难</option></select></label>
            <label>出题要求<textarea v-model.trim="dialog.instruction" rows="3" maxlength="2000" placeholder="例如：解答题包含一题 Python 编程，覆盖函数的参数与返回值"></textarea></label>
            <MapSources v-model="dialog.sources" :resources="resources" />
          </template>
        </template>
        <p v-if="formError" class="error" role="alert">{{ formError }}</p>
        <div class="dialog-actions">
          <button type="button" class="button secondary" :disabled="busy" @click="dialog = null">取消</button>
          <button type="submit" class="button" :class="dialog.mode === 'delete' ? 'danger' : 'primary'" :disabled="busy || (dialog.mode === 'import' && !dialog.file)">{{ busy ? '正在处理…' : labels[dialog.mode] }}</button>
        </div>
      </form>
    </Modal>
  </div>
</template>
