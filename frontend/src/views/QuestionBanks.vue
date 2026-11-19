<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Archive, ArrowUpRight, BookOpenCheck, Copy, Pencil, Plus, Search, Sparkles, Trash2 } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import { bankStatuses, uid } from '../questionBanks'
import { course, courseId } from '../session'
import BankCover from '../components/BankCover.vue'
import Empty from '../components/Empty.vue'
import Modal from '../components/Modal.vue'
import '../questionBanks.css'
const router = useRouter()
const banks = ref([])
const loading = ref(true)
const error = ref('')
const modal = ref(null)
const busy = ref(false)
const search = ref('')
const filter = ref('current')
const visible = computed(() => banks.value.filter((bank) => (filter.value === 'current' ? !bank.archived : filter.value === 'archived' ? bank.archived : bank.status === filter.value)
  && `${bank.title} ${bank.description} ${bank.tags.join(' ')}`.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
async function load() { banks.value = await api('/question-banks?course_id='+courseId.value) }
onMounted(async () => { try { await load() } catch (failure) { error.value = failure.message } finally { loading.value = false } })
function open(mode, bank = null) { error.value = ''; modal.value = { mode, bank, title: bank?.title || '', request_key: uid(), error: '' } }
async function submit() {
  busy.value = true; modal.value.error = ''
  try {
    const m = modal.value
    if (m.mode === 'delete') await api(`/question-banks/${m.bank.id}`, { method:'DELETE' })
    else if (m.mode === 'copy') {
      const copied = await api(`/question-banks/${m.bank.id}/copy`, { method:'POST',body:{request_key:m.request_key} })
      await router.push('/question-banks/'+copied.id); return
    } else if (['rename','archive','restore'].includes(m.mode)) {
      const row = await api('/question-banks/'+m.bank.id)
      if(m.mode!=='rename') await api('/question-banks/'+row.id+'/status', {method:'PATCH',body:{revision:row.revision,archived:m.mode==='archive'}})
      else await api('/question-banks/'+row.id, { method:'PUT',body:{revision:row.revision,title:m.title,description:row.description,tags:row.tags,
        cover:row.cover,sections:row.sections,materials:row.materials,sources:row.sources,archived:row.archived} })
    } else {
      const bank = await api('/question-banks', { method:'POST', body:{ course_id:courseId.value,title:m.title } })
      await router.push('/question-banks/'+bank.id+(m.mode==='ai'?'?generate=1':m.mode==='import'?'?import=1':'')); return
    }
    await load(); modal.value = null
  } catch (failure) { modal.value.error = failure.message }
  finally { busy.value = false }
}
const labels = { new:'新建题库',ai:'AI 生成题库',import:'导入题目',rename:'重命名题库',copy:'复制题库',archive:'归档题库',restore:'恢复题库',delete:'删除草稿题库' }
</script>
<template>
  <div class="page bank-library">
    <header class="page-heading"><div><span class="bank-eyebrow">QUESTION BANKS</span><h1>在线题库</h1><p>{{ course.name }} · 为自主练习组织题目与答案</p></div>
      <div class="actions"><button class="button secondary" @click="open('import')">导入题目</button><button class="button secondary" @click="open('new')"><Plus :size="17" /> 新建题库</button><button class="button primary" @click="open('ai')"><Sparkles :size="17" /> AI 生成题库</button></div></header>
    <div class="bank-library-tools"><div class="bank-tab-row"><button v-for="[key,label] in [['current','全部题库'],['published','已发布'],['draft','草稿'],['offline','已下架'],['archived','已归档']]" :key="key" :class="{active:filter===key}" @click="filter=key">{{ label }}</button></div>
      <label class="search"><Search :size="17" /><input v-model="search" type="search" aria-label="搜索题库" placeholder="搜索题库、标签"></label></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="loading" class="empty-state" role="status">正在加载题库…</div>
    <div v-else-if="visible.length" class="bank-cover-grid"><article v-for="bank in visible" :key="bank.id" class="bank-library-card panel">
      <RouterLink :to="'/question-banks/'+bank.id" class="bank-card-cover"><BankCover :bank="bank" :course="course.name" thumbnail /><span class="bank-card-open"><ArrowUpRight :size="22" /></span></RouterLink>
      <div class="bank-card-info"><div class="section-heading"><RouterLink :to="'/question-banks/'+bank.id"><h3>{{ bank.title }}</h3></RouterLink><span class="bank-chip" :class="{live:bank.status==='published'}">{{ bankStatuses[bank.status] }}</span></div>
        <p class="muted bank-card-description">{{ bank.description || '按章节组织知识点，随时开始练习。' }}</p>
        <div class="bank-card-meta"><span>{{ bank.question_count }} 道题</span><span v-if="bank.release">发布 v{{ bank.release.number }}</span><span v-if="bank.has_unpublished_changes && bank.status==='published'">有未发布修改</span></div>
        <footer><small class="muted">{{ formatDate(bank.updated_at) }}</small><div class="actions"><button class="button subtle icon-only" aria-label="重命名题库" title="重命名" @click="open('rename',bank)"><Pencil :size="15" /></button><button class="button subtle icon-only" aria-label="复制题库" title="复制为新草稿" @click="open('copy',bank)"><Copy :size="15" /></button>
          <button class="button subtle icon-only" :aria-label="bank.archived?'恢复题库':'归档题库'" :title="bank.archived?'恢复':'归档'" @click="open(bank.archived?'restore':'archive',bank)"><Archive :size="15" /></button>
          <button v-if="!bank.release" class="button subtle icon-only danger-text" aria-label="删除草稿题库" title="删除" @click="open('delete',bank)"><Trash2 :size="15" /></button></div></footer></div>
    </article></div>
    <Empty v-else :title="search ? '没有匹配的题库' : '为这门课创建第一份题库'" detail="从空白开始，或挂载资料让 AI 起草题目与解析。"><BookOpenCheck /></Empty>
    <Modal :open="!!modal" :title="labels[modal?.mode]" @close="!busy && (modal=null)"><form v-if="modal" class="stack" @submit.prevent="submit">
      <label v-if="['new','ai','import','rename'].includes(modal.mode)">题库名称<input v-model.trim="modal.title" required maxlength="160" placeholder="例如：Python 函数与参数练习"></label>
      <p v-else>{{ modal.mode==='copy'?'将题目、答案、封面和章节复制为未发布草稿。':modal.mode==='archive'?'归档后将下架已发布内容，并保留版本记录。':modal.mode==='restore'?'恢复后可继续编辑，不会自动重新发布。':'确定删除此草稿及其题目？' }}</p>
      <p v-if="['new','ai','import'].includes(modal.mode)" class="muted">创建后自动配置默认封面，可继续修改封面、章节和资料。</p>
      <p v-if="modal.error" class="error" role="alert">{{ modal.error }}</p><button class="button primary" :disabled="busy">{{ busy?'正在处理…':'确认' }}</button>
    </form></Modal>
  </div>
</template>
