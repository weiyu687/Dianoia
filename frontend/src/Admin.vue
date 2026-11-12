<script setup>
import { onMounted, ref, watch } from 'vue'
import { Download, FileSpreadsheet, LogOut, Upload, Users } from 'lucide-vue-next'
import { api, download } from './api'
import { logout, restore, user } from './session'
import Brand from './components/Brand.vue'
import Login from './components/Login.vue'
import Modal from './components/Modal.vue'
import ThemeButton from './components/ThemeButton.vue'

const ready = ref(false)
const overview = ref(null)
const workbook = ref(null)
const result = ref(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const account = ref(null)
const accountError = ref('')
const counts = [
  ['teachers', '教师'], ['students', '学生'], ['courses', '课程'], ['classes', '教学班'],
]

async function load() {
  try { overview.value = await api('/admin/overview') }
  catch (failure) { error.value = failure.message }
}
watch(user, (profile) => {
  if (profile) load()
  else { overview.value = null; workbook.value = null; result.value = null; notice.value = '' }
})
onMounted(async () => {
  try { await restore('admin') }
  catch (failure) { error.value = failure.message }
  finally { ready.value = true }
})

async function template() {
  try { await download('/admin/template', 'dianoia-import.xlsx') }
  catch (failure) { error.value = failure.message }
}

async function inspect(apply) {
  if (!workbook.value || busy.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const body = new FormData()
    body.append('file', workbook.value)
    body.append('apply', String(apply))
    result.value = await api('/admin/import', { method: 'POST', body })
    if (result.value.applied) {
      notice.value = '数据已导入。新教师账号可在下方开通。'
      await load()
    }
  } catch (failure) { error.value = failure.message }
  finally { busy.value = false }
}

function choose(event) {
  workbook.value = event.target.files[0]
  result.value = null
  notice.value = ''
}

async function saveAccount() {
  accountError.value = ''
  try {
    const { id, enabled, password } = account.value
    await api(`/admin/teachers/${id}/account`, { method: 'PUT', body: { enabled, password: password || null } })
    account.value = null
    await load()
  } catch (failure) { accountError.value = failure.message }
}

async function signOut() {
  try { await logout() }
  catch (failure) { error.value = failure.message }
}
</script>

<template>
  <div v-if="!ready" class="full-state" role="status">正在加载学校管理</div>
  <Login v-else-if="!user" role="admin" />
  <div v-else class="admin-shell">
    <header class="topbar admin-top"><Brand subtitle="学校管理" /><div class="actions"><ThemeButton /><span class="muted">{{ user.name }}</span><button class="button subtle" @click="signOut"><LogOut :size="16" /> 退出</button></div></header>
    <main class="page admin-page">
      <header class="page-heading"><div><h1>学校管理</h1><p>导入教学数据并管理教师账号。</p></div></header>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <p v-if="notice" class="success" role="status">{{ notice }}</p>
      <div v-if="overview" class="school-stats"><div v-for="[key, label] in counts" :key="key" class="panel"><span>{{ label }}</span><strong>{{ overview[key] }}</strong></div></div>
      <section class="panel admin-import stack">
        <div class="section-heading"><h2><FileSpreadsheet :size="20" /> 教学数据导入</h2><button class="button secondary" @click="template"><Download :size="16" /> 下载 Excel 模板</button></div>
        <div class="actions"><input type="file" accept=".xlsx" aria-label="选择教学数据工作簿" @change="choose"><button class="button primary" :disabled="!workbook || busy" @click="inspect(false)"><Upload :size="16" /> 预检工作簿</button></div>
        <div v-if="result" class="stack">
          <div class="table-scroll"><table class="data-table"><thead><tr><th>工作表</th><th>新增</th><th>更新</th><th>无变化</th></tr></thead><tbody><tr v-for="(summary, name) in result.rows" :key="name"><td>{{ name }}</td><td>{{ summary.added }}</td><td>{{ summary.updated }}</td><td>{{ summary.unchanged }}</td></tr></tbody></table></div>
          <ul v-if="result.errors.length" class="error" role="alert"><li v-for="item in result.errors" :key="item">{{ item }}</li></ul>
          <div class="actions"><button class="button primary" :disabled="busy || result.errors.length > 0 || result.applied" @click="inspect(true)">确认导入</button></div>
        </div>
      </section>
      <section class="admin-accounts">
        <header class="section-heading"><h2><Users :size="20" /> 教师账号</h2></header>
        <div v-if="overview?.accounts.length" class="table-scroll"><table class="data-table"><thead><tr><th>姓名</th><th>工号</th><th>状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="item in overview.accounts" :key="item.id"><td>{{ item.name }}</td><td>{{ item.username }}</td><td><span class="status-tag" :class="{ ready: item.enabled }">{{ item.enabled ? '已开通' : '停用' }}</span></td><td><button class="button secondary" @click="accountError = ''; account = { ...item, password: '' }">账号设置</button></td></tr></tbody>
        </table></div>
        <p v-else class="muted">还没有教师账号。</p>
      </section>
    </main>
    <Modal :open="!!account" :title="`账号设置 · ${account?.name || ''}`" @close="account = null">
      <form v-if="account" class="stack" @submit.prevent="saveAccount">
        <label class="checkbox-label"><input v-model="account.enabled" type="checkbox"> 允许登录教师端</label>
        <label>设置或重置密码<input v-model="account.password" type="password" autocomplete="new-password" minlength="10" maxlength="128" placeholder="至少 10 字符，留空保留原密码"></label>
        <p v-if="accountError" class="error" role="alert">{{ accountError }}</p><div class="dialog-actions"><button type="submit" class="button primary">保存设置</button></div>
      </form>
    </Modal>
  </div>
</template>
