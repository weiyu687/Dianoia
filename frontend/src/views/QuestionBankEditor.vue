<script setup>
import { computed, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { ArrowDown, ArrowLeft, ArrowUp, Check, ChevronRight, Eye, FileUp, FolderPlus, Image, Layers, Plus, Search, Settings2, Sparkles, Trash2, UploadCloud, X } from 'lucide-vue-next'
import { api, formatDate } from '../api'
import { bankKinds, bankStatuses, clone, docText, emptyDoc, freshQuestion, sectionsFlat, uid } from '../questionBanks'
import { course, courseId } from '../session'
import BankCoverEditor from '../components/BankCoverEditor.vue'
import BankQuestionForm from '../components/BankQuestionForm.vue'
import BankQuestionPreview from '../components/BankQuestionPreview.vue'
import BankRichEditor from '../components/BankRichEditor.vue'
import MapSources from '../components/MapSources.vue'
import Modal from '../components/Modal.vue'
import '../questionBanks.css'

const route = useRoute(), router = useRouter()
const path = '/question-banks/'+route.params.id
const bank = ref(null), resources = ref([]), exams = ref([]), themes = ref([])
const error = ref(''), formError = ref(''), loading = ref(true), busy = ref(false), dirty = ref(false)
const rows = ref([]), total = ref(0), page = ref(1), section = ref(''), kind = ref(''), search = ref(''), pending = ref(false)
const selected = ref(null), checked = ref([]), dialog = ref(null), form = ref(null)
const mediaUploads = ref(0)
provide('bank-image-uploads', (delta) => { mediaUploads.value = Math.max(0, mediaUploads.value + delta) })
const chapters = computed(() => bank.value ? sectionsFlat(bank.value.sections) : [])
const activeJobs = computed(() => bank.value?.jobs.filter((j) => ['queued','running'].includes(j.status)) || [])
let timer, searchTimer, polling = false, disposed = false, listRequest = 0
async function loadBank() { const value = await api(path); if (!disposed) bank.value = value }
async function loadQuestions() {
  const request = ++listRequest
  const parameters = new URLSearchParams({ page:String(page.value),limit:'30',q:search.value,pending:String(pending.value) })
  if(section.value) parameters.set('section_id',section.value)
  if(kind.value) parameters.set('kind',kind.value)
  const response = await api(path+'/questions?'+parameters)
  if (!disposed && request === listRequest) { rows.value=response.items;total.value=response.total;checked.value=checked.value.filter(id=>response.items.some(item=>item.id===id)) }
}
function canDiscard() { return (!dirty.value && !mediaUploads.value) || window.confirm(mediaUploads.value ? '图片仍在上传，确定离开当前编辑？' : '当前题目尚未保存，确定放弃修改？') }
async function selectQuestion(id) {
  if (!canDiscard()) return
  try { selected.value = await api(path+'/questions/'+id);dirty.value=false;formError.value='' } catch(failure) { error.value=failure.message }
}
function newQuestion() {
  if(!canDiscard()) return
  selected.value={ id:null,revision:1,request_key:uid(),question:freshQuestion(section.value || null) }; dirty.value=false;formError.value=''
}
async function saveQuestion(question) {
  if(busy.value || mediaUploads.value) return
  busy.value=true;formError.value=''
  try {
    selected.value=await api(path+'/questions'+(selected.value.id?'/'+selected.value.id:''), {
      method:selected.value.id?'PUT':'POST',body:selected.value.id?{revision:selected.value.revision,question}:question,
      headers:selected.value.id?{}:{'Idempotency-Key':selected.value.request_key},
    })
    dirty.value=false
    await Promise.all([loadBank(),loadQuestions()])
  } catch(failure) {formError.value=failure.message} finally {busy.value=false}
}
function bankBody(value) { return Object.fromEntries(['revision','title','description','tags','cover','sections','materials','sources','archived'].map((k)=>[k,clone(value[k])])) }
async function saveDetails(value) {
  if(mediaUploads.value){dialog.value.error='图片仍在上传，请稍候再保存';return}
  busy.value=true;dialog.value.error=''
  try {bank.value=await api(path,{method:'PUT',body:bankBody(value)});dialog.value=null;await loadQuestions()}
  catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
function openSettings(tab='general') { dialog.value={mode:'settings',tab,data:clone(bank.value),tags:bank.value.tags.join('，'),error:''} }
function addSection() {dialog.value.data.sections.push({id:uid(),title:'新章节',parent_id:null})}
function swapSection(index,delta){const list=dialog.value.data.sections;if(!list[index+delta])return;[list[index],list[index+delta]]=[list[index+delta],list[index]]}
function openGenerator(){dialog.value={mode:'generate',request_key:uid(),groups:[{kind:'single',count:5}],section_id:section.value||null,sources:clone(bank.value.sources),knowledge:'',difficulty:'适中',language:'中文',explanation:'详细',instruction:'',error:''}}
function addGroup(){const next=Object.keys(bankKinds).find((k)=>!dialog.value.groups.some((g)=>g.kind===k));if(next)dialog.value.groups.push({kind:next,count:3})}
async function startGeneration(){
  busy.value=true;dialog.value.error=''
  try{const {mode,error,...body}=dialog.value;await api(path+'/jobs',{method:'POST',body});dialog.value=null;await loadBank()}
  catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
async function controlJob(job,operation){try{await api(`${path}/jobs/${job.id}/${operation}`,{method:'POST'});await loadBank()}catch(failure){error.value=failure.message}}
function openImport(){dialog.value={mode:'import',source:'word',exam_id:exams.value[0]?.id||'',section_id:section.value||null,result:null,chosen:[],request_key:uid(),error:''}}
async function parseImport(file){
  busy.value=true;dialog.value.error=''
  try{
    let result
    if(dialog.value.source==='word'){if(!file)throw new Error('请先选择 Word 文件');const body=new FormData();body.set('file',file);result=await api(path+'/imports/word',{method:'POST',body})}
    else result=await api(path+'/imports/exams/'+dialog.value.exam_id)
    dialog.value.result=result;dialog.value.chosen=result.candidates.map((c)=>c.key)
  }catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
async function adoptImport(){
  busy.value=true;dialog.value.error=''
  try{const d=dialog.value;const questions=d.result.candidates.filter((c)=>d.chosen.includes(c.key)).map((c)=>({...c.question,confirmed:false,section_id:d.section_id}));
    await api(path+'/imports/adopt',{method:'POST',body:{questions,request_key:d.request_key}});dialog.value=null;await Promise.all([loadBank(),loadQuestions()])
  }catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
async function openPublish(){
  if(dirty.value||mediaUploads.value){error.value='请先完成图片上传并保存当前题目，再预览或发布';return}
  error.value=''
  try{await loadBank();const check=await api(path+'/preflight');dialog.value={mode:'publish',check,revision:bank.value.revision,request_key:uid(),audience:bank.value.release?.class_codes.length?'classes':'course',class_codes:clone(bank.value.release?.class_codes||[]),error:''}}
  catch(failure){error.value=failure.message}
}
async function publish(){
  busy.value=true;dialog.value.error=''
  try{const d=dialog.value;if(d.audience==='classes'&&!d.class_codes.length)throw new Error('请至少选择一个教学班');
    const result=await api(path+'/publish',{method:'POST',body:{revision:d.revision,request_key:d.request_key,class_codes:d.audience==='course'?[]:d.class_codes}});bank.value=result.bank;dialog.value=null
  }catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
function openPreview(releaseId){if(dirty.value||mediaUploads.value){error.value='请先完成图片上传并保存当前题目，再预览';return}router.push(path+'/preview'+(releaseId?'?release_id='+releaseId:''))}
async function withdraw(){
  busy.value=true;dialog.value.error=''
  try{const d=dialog.value;bank.value=await api(path+'/withdraw',{method:'POST',body:{revision:bank.value.revision,release_id:d.release.id,emergency:d.emergency}});dialog.value=null}
  catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
async function bulk(action,ids=checked.value,extra={}){
  if(!ids.length||!canDiscard())return
  busy.value=true;error.value=''
  try{bank.value=await api(path+'/bulk',{method:'POST',body:{bank_revision:bank.value.revision,ids,action,...extra}});dirty.value=false;checked.value=[];
    if(selected.value?.id&&action==='delete'&&ids.includes(selected.value.id))selected.value=null
    else if(selected.value?.id&&ids.includes(selected.value.id))selected.value=await api(path+'/questions/'+selected.value.id)
    await loadQuestions();dialog.value=null
  }catch(failure){error.value=failure.message}finally{busy.value=false}
}
function openRevise(){if(dirty.value){formError.value='请先保存当前修改，再使用 AI 修改本题';return}dialog.value={mode:'revise',action:'改写题干',instruction:'',candidate:null,error:''}}
async function generateRevision(){
  busy.value=true;dialog.value.error=''
  try{const result=await api(path+`/questions/${selected.value.id}/revise`,{method:'POST',body:{revision:selected.value.revision,mode:dialog.value.action,instruction:dialog.value.instruction}});dialog.value.candidate=result}
  catch(failure){dialog.value.error=failure.message}finally{busy.value=false}
}
async function adoptRevision(){const value=dialog.value.candidate.question;value.confirmed=false;dialog.value=null;await saveQuestion(value)}
function unload(event){if(dirty.value||mediaUploads.value){event.preventDefault();event.returnValue=''}}
onBeforeRouteLeave(()=>canDiscard())
onMounted(async()=>{
  try{
    const [,files,papers,styles]=await Promise.all([loadBank(),api('/resources?course_id='+courseId.value),api('/exams?course_id='+courseId.value),api('/question-banks/themes')])
    resources.value=files.filter((f)=>f.status==='ready'&&f.page_count);exams.value=papers;themes.value=styles
    await loadQuestions();if(rows.value.length)await selectQuestion(rows.value[0].id)
    if(route.query.generate)openGenerator();else if(route.query.import)openImport()
    timer=setInterval(async()=>{
      if(!activeJobs.value.length||polling)return
      polling=true
      try{await Promise.all([loadBank(),loadQuestions()])}catch(failure){error.value=failure.message}finally{polling=false}
    },2500)
    window.addEventListener('beforeunload',unload)
  }catch(failure){error.value=failure.message}finally{loading.value=false}
})
watch([section,kind,pending],async()=>{page.value=1;try{await loadQuestions()}catch(f){error.value=f.message}})
watch(page,async()=>{try{await loadQuestions()}catch(f){error.value=f.message}})
watch(search,()=>{clearTimeout(searchTimer);searchTimer=setTimeout(async()=>{page.value=1;try{await loadQuestions()}catch(f){error.value=f.message}},300)})
onBeforeUnmount(()=>{disposed=true;clearInterval(timer);clearTimeout(searchTimer);window.removeEventListener('beforeunload',unload)})
const titles={cover:'题库封面',settings:'题库设置',generate:'AI 生成练习题',import:'导入候选题',publish:'发布题库',history:'发布版本',withdraw:'下架发布版本',revise:'AI 修改本题',move:'批量移动题目',tags:'批量设置标签',delete:'删除所选题目'}
</script>

<template>
  <div class="page bank-editor-page">
    <div v-if="loading" class="empty-state">正在打开题库…</div><p v-if="error" class="error" role="alert">{{ error }} <button class="button subtle" @click="error=''">关闭提示</button></p>
    <template v-if="bank">
      <header class="bank-editor-header"><div><RouterLink class="text-link" to="/question-banks"><ArrowLeft :size="15" /> 在线题库</RouterLink><h1>{{ bank.title }}</h1>
        <div class="actions muted"><span class="bank-chip">{{ bankStatuses[bank.status] }}</span><span>{{ bank.question_count }} 道题</span><span>{{ dirty?'有未保存修改':'内容已保存' }}</span><span v-if="bank.has_unpublished_changes&&bank.status==='published'">有未发布修改</span></div></div>
        <div class="actions"><button class="button secondary" @click="dialog={mode:'cover',error:''}"><Image :size="16" /> 封面</button><button class="button secondary" @click="openSettings()"><Settings2 :size="16" /> 设置</button>
          <button class="button secondary" @click="openPreview()"><Eye :size="16" /> 预览</button><button class="button primary" :disabled="bank.archived||busy" @click="openPublish"><UploadCloud :size="16" />{{ bank.release?'发布更新':'发布题库' }}</button></div></header>
      <div v-for="job in bank.jobs.filter(j=>['queued','running','failed','cancelled'].includes(j.status)).slice(0,3)" :key="job.id" class="bank-job panel"><div class="stack"><strong>{{ job.stage }}</strong><progress :value="job.completed" :max="job.total"></progress><small class="muted">{{ job.completed }} / {{ job.total }} 题 · {{ job.error || '生成结果保存为待核对草稿' }}</small></div>
        <button v-if="['queued','running'].includes(job.status)" class="button subtle" @click="controlJob(job,'cancel')">取消</button><button v-else class="button secondary" @click="controlJob(job,'retry')">继续生成</button></div>
      <div class="bank-editor-layout">
        <aside class="bank-outline panel"><div class="section-heading"><h3>章节目录</h3><button class="button subtle icon-only" aria-label="管理章节" @click="openSettings('sections')"><FolderPlus :size="17" /></button></div>
          <button :class="{active:!section}" @click="section=''">全部题目 <small>{{ bank.question_count }}</small></button><button v-for="s in chapters" :key="s.id" :style="{paddingLeft:14+s.depth*14+'px'}" :class="{active:section===s.id}" @click="section=s.id"><ChevronRight :size="12" />{{ s.title }}</button>
          <div class="bank-outline-bottom"><button class="button subtle" @click="openSettings('materials')"><Layers :size="16" /> 共享材料 {{ bank.materials.length }}</button><button class="button subtle" @click="dialog={mode:'history',error:''}">发布版本 {{ bank.releases.length }}</button></div></aside>
        <div class="bank-authoring-column"><section class="panel bank-question-list"><div class="bank-question-list-tools"><div class="actions"><label class="search"><Search :size="16" /><input v-model="search" type="search" aria-label="搜索题目" placeholder="搜索题干、知识点"></label>
            <select v-model="kind" aria-label="筛选题型"><option value="">所有题型</option><option v-for="(name,key) in bankKinds" :key="key" :value="key">{{ name }}</option></select><label class="bank-check"><input v-model="pending" type="checkbox">待确认</label></div>
            <div class="actions"><button class="button subtle" :disabled="bank.archived" @click="openImport"><FileUp :size="15" /> 导入</button><button class="button secondary" :disabled="bank.archived" @click="newQuestion"><Plus :size="15" /> 新建题目</button><button class="button primary" :disabled="bank.archived" @click="openGenerator"><Sparkles :size="15" /> AI 生成</button></div></div>
          <div v-if="checked.length" class="bank-bulk-bar"><span>已选 {{ checked.length }} 题</span><button @click="dialog={mode:'move',section_id:null,error:''}">移动</button><button @click="dialog={mode:'tags',tags:'',error:''}">标签</button><button @click="bulk('exclude')">暂不发布</button><button @click="bulk('include')">参与发布</button><button class="danger-text" @click="dialog={mode:'delete',error:''}">删除</button></div>
          <div v-if="rows.length" class="bank-question-rows"><div v-for="(row,index) in rows" :key="row.id" class="bank-question-row" :class="{selected:selected?.id===row.id}">
            <input v-model="checked" type="checkbox" :value="row.id" :aria-label="'选择题目 '+row.excerpt.slice(0,20)"><button class="bank-question-select" @click="selectQuestion(row.id)"><span><b>{{ bankKinds[row.kind] }}</b><small>{{ row.confirmed?'已确认':'待确认' }}{{ row.included?'':' · 暂不发布' }}</small></span><p>{{ row.excerpt || '未填写题干' }}</p></button>
            <div class="bank-row-order"><button aria-label="上移题目" :disabled="index===0||busy||bank.archived" @click="bulk('reorder',[row.id,rows[index-1].id])"><ArrowUp :size="14" /></button><button aria-label="下移题目" :disabled="index===rows.length-1||busy||bank.archived" @click="bulk('reorder',[rows[index+1].id,row.id])"><ArrowDown :size="14" /></button></div></div></div>
          <p v-else class="empty-state">{{ bank.question_count?'没有符合条件的题目':'尚无题目，可以手工录入或根据资料生成。' }}</p>
          <div v-if="total>30" class="bank-pagination"><button class="button subtle" :disabled="page===1" @click="page--">上一页</button><span>{{ page }} / {{ Math.ceil(total/30) }}</span><button class="button subtle" :disabled="page*30>=total" @click="page++">下一页</button></div></section>
          <section v-if="selected&&!bank.archived" class="panel bank-edit-surface"><BankQuestionForm ref="form" :value="selected" :bank="bank" :resources="resources" :busy="busy||mediaUploads>0" :error="formError" @dirty="dirty=$event" @save="saveQuestion" @revise="openRevise" /></section>
          <div v-else class="panel bank-editor-empty"><Plus :size="28" /><h2>{{ bank.archived?'此题库已归档':'选择或新建一道题目' }}</h2><p class="muted">题目、参考答案和解析在同一处编写，确认后再发布。</p></div>
        </div>
      </div>
      <Modal :open="!!dialog" :title="titles[dialog?.mode]" :wide="!['move','tags','delete','withdraw'].includes(dialog?.mode)" @close="!busy&&(dialog=null)">
        <template v-if="dialog">
          <BankCoverEditor v-if="dialog.mode==='cover'" :bank="bank" :course="course.name" :themes="themes" :busy="busy" @apply="saveDetails({...bank,cover:$event})" />
          <div v-else-if="dialog.mode==='settings'" class="stack"><div class="bank-tab-row"><button v-for="[key,label] in [['general','基本信息'],['sections','章节'],['materials','共享材料'],['sources','参考资料']]" :key="key" :class="{active:dialog.tab===key}" @click="dialog.tab=key">{{ label }}</button></div>
            <template v-if="dialog.tab==='general'"><label>题库名称<input v-model="dialog.data.title" maxlength="160"></label><label>简介<textarea v-model="dialog.data.description" rows="3" maxlength="3000"></textarea></label><label>标签<input v-model="dialog.tags" placeholder="用逗号分隔" maxlength="490"></label><label class="bank-check"><input v-model="dialog.data.archived" type="checkbox">归档题库（会下架已发布版本）</label></template>
            <template v-else-if="dialog.tab==='sections'"><div v-for="(s,index) in dialog.data.sections" :key="s.id" class="bank-section-edit"><input v-model="s.title" aria-label="章节名称" maxlength="160"><select v-model="s.parent_id" aria-label="父章节"><option :value="null">顶级章节</option><option v-for="parent in dialog.data.sections.filter(p=>p.id!==s.id)" :key="parent.id" :value="parent.id">{{ parent.title }}</option></select><button class="button subtle icon-only" aria-label="上移章节" :disabled="index===0" @click="swapSection(index,-1)"><ArrowUp :size="15" /></button><button class="button subtle icon-only" aria-label="下移章节" :disabled="index===dialog.data.sections.length-1" @click="swapSection(index,1)"><ArrowDown :size="15" /></button><button class="button subtle icon-only" aria-label="删除章节" :disabled="dialog.data.sections.some(p=>p.parent_id===s.id)" @click="dialog.data.sections.splice(index,1)"><Trash2 :size="15" /></button></div><button class="button secondary" @click="addSection"><Plus :size="16" /> 添加章节</button><p class="muted">可选择父章节建立子章节。删除前需移动章节中的题目。</p></template>
            <template v-else-if="dialog.tab==='materials'"><div v-for="(m,index) in dialog.data.materials" :key="m.id" class="panel bank-material-editor stack"><div class="actions"><input v-model="m.title" aria-label="材料名称" maxlength="160"><button class="button subtle" @click="dialog.data.materials.splice(index,1)">移除材料</button></div><BankRichEditor v-model="m.body" :bank-id="bank.id" label="共享材料正文" /></div><button class="button secondary" @click="dialog.data.materials.push({id:uid(),title:'新材料',body:emptyDoc()})"><Plus :size="16" /> 添加共用材料</button></template>
            <MapSources v-else v-model="dialog.data.sources" :resources="resources" />
            <button class="button primary" :disabled="busy" @click="saveDetails({...dialog.data,tags:dialog.tags.split(/[,，、]/).map(t=>t.trim()).filter(Boolean)})">{{ busy?'正在保存…':'保存设置' }}</button>
          </div>
          <form v-else-if="dialog.mode==='generate'" class="stack" @submit.prevent="startGeneration"><p class="muted">AI 同时起草题目、答案和解析。生成后保留为待核对草稿。</p><MapSources v-model="dialog.sources" :resources="resources" />
            <div class="section-heading"><strong>题型与数量</strong><button class="button secondary" type="button" :disabled="dialog.groups.length===5" @click="addGroup">添加题型</button></div>
            <div v-for="(group,index) in dialog.groups" :key="index" class="actions"><select v-model="group.kind" aria-label="生成题型"><option v-for="(name,key) in bankKinds" :key="key" :value="key" :disabled="key!==group.kind&&dialog.groups.some(g=>g.kind===key)">{{ name }}</option></select><label>数量<input v-model.number="group.count" type="number" min="1" max="20" required></label><button class="button subtle" type="button" :disabled="dialog.groups.length===1" @click="dialog.groups.splice(index,1)">移除</button></div>
            <div class="bank-fields three"><label>目标章节<select v-model="dialog.section_id"><option :value="null">未分类</option><option v-for="s in chapters" :key="s.id" :value="s.id">{{ '　'.repeat(s.depth) }}{{ s.title }}</option></select></label><label>难度<select v-model="dialog.difficulty"><option>基础</option><option>适中</option><option>较难</option></select></label><label>语言<select v-model="dialog.language"><option>中文</option><option>英文</option><option>中英双语</option></select></label></div>
            <label>知识点<input v-model="dialog.knowledge" maxlength="1000" placeholder="例如：函数定义、位置参数、默认参数"></label><label>解析详略<select v-model="dialog.explanation"><option>详细</option><option>简明</option></select></label><label>补充要求<textarea v-model="dialog.instruction" rows="3" maxlength="3000"></textarea></label><button class="button primary" :disabled="busy||dialog.groups.reduce((n,g)=>n+g.count,0)>20">{{ busy?'正在提交…':'开始生成（每批最多 20 题）' }}</button>
          </form>
          <div v-else-if="dialog.mode==='import'" class="stack"><div class="bank-tab-row"><button :class="{active:dialog.source==='word'}" @click="dialog.source='word';dialog.result=null">上传 Word</button><button :class="{active:dialog.source==='exam'}" @click="dialog.source='exam';dialog.result=null">已有试卷</button></div>
            <label v-if="dialog.source==='word'">DOC / DOCX 原卷<input type="file" accept=".doc,.docx" :disabled="busy" @change="parseImport($event.target.files[0])"></label><div v-else class="actions"><select v-model="dialog.exam_id"><option value="">选择当前课程试卷</option><option v-for="exam in exams" :key="exam.id" :value="exam.id">{{ exam.title }}</option></select><button class="button secondary" :disabled="busy||!dialog.exam_id" @click="parseImport()">提取已确认题目</button></div>
            <p v-if="busy" class="muted" role="status">正在处理，请稍候…</p><template v-if="dialog.result"><p v-for="(note,index) in dialog.result.warnings" :key="index" class="error">{{ note }}</p>
              <div class="bank-import-candidates"><label v-for="(c,index) in dialog.result.candidates" :key="c.key"><input v-model="dialog.chosen" type="checkbox" :value="c.key"><div><strong>{{ index+1 }}. {{ bankKinds[c.question.kind] }}</strong><p>{{ docText(c.question.body).slice(0,220) }}</p><small v-for="(note,i) in c.warnings" :key="i" class="muted">{{ note }}；</small></div></label></div>
              <label>导入章节<select v-model="dialog.section_id"><option :value="null">未分类</option><option v-for="s in chapters" :key="s.id" :value="s.id">{{ s.title }}</option></select></label><p class="muted">导入后逐题核对题干、选项、公式和答案，确认前不能发布。</p><button class="button primary" :disabled="busy||!dialog.chosen.length" @click="adoptImport">导入 {{ dialog.chosen.length }} 道候选题</button></template></div>
          <div v-else-if="dialog.mode==='publish'" class="stack"><p>{{ dialog.check.question_count }} 道题参与本次发布。{{ bank.release?'创建新的发布版本，草稿不会覆盖已发布内容。':'发布后对选定范围内的学生可见。' }}</p>
            <div v-if="dialog.check.issues.length" class="bank-preflight"><strong>请先处理以下问题</strong><button v-for="(issue,index) in dialog.check.issues" :key="index" @click="issue.question_id&&(dialog=null,selectQuestion(issue.question_id))"><span>{{ issue.excerpt }}</span><small>{{ issue.messages.join('；') }}</small></button></div>
            <label>发布范围<select v-model="dialog.audience"><option value="course">当前课程全部教学班</option><option value="classes">指定教学班</option></select></label><div v-if="dialog.audience==='classes'" class="stack"><label v-for="group in bank.classes" :key="group.code" class="bank-check"><input v-model="dialog.class_codes" type="checkbox" :value="group.code">{{ group.name }}</label></div>
            <p v-if="!bank.classes.length" class="error">当前课程尚无教学班，请先在学校管理端录入。</p><button class="button primary" :disabled="busy||!dialog.check.ready||!bank.classes.length" @click="publish">{{ busy?'正在发布…':'确认发布' }}</button></div>
          <div v-else-if="dialog.mode==='history'" class="stack"><p v-if="!bank.releases.length" class="muted">尚未发布，先核对题目与答案。</p><div v-for="release in bank.releases" :key="release.id" class="bank-release-row"><div><strong>发布版本 v{{ release.number }}</strong><p class="muted">{{ formatDate(release.created_at) }} · {{ {active:'已发布',superseded:'已更新',closed:'已下架',revoked:'已撤回'}[release.status] }}</p></div><div class="actions"><button class="button secondary" @click="openPreview(release.id)">预览此版本</button><button v-if="['active','superseded'].includes(release.status)" class="button subtle danger-text" @click="dialog={mode:'withdraw',release,emergency:false,error:''}">下架</button></div></div></div>
          <div v-else-if="dialog.mode==='withdraw'" class="stack"><p>下架 v{{ dialog.release.number }} 后将不再允许新开练习，发布内容和历史记录保留。</p><label class="bank-check"><input v-model="dialog.emergency" type="checkbox">紧急撤回，同时停止已有练习继续访问</label><button class="button primary" :disabled="busy" @click="withdraw">确认下架</button></div>
          <div v-else-if="dialog.mode==='revise'" class="stack"><label>修改方式<select v-model="dialog.action"><option v-for="mode in ['改写题干','优化干扰项','调整难度','补充答案与解析','替换本题']" :key="mode">{{ mode }}</option></select></label><label>具体要求<textarea v-model="dialog.instruction" rows="3" maxlength="3000" placeholder="例如：保留知识点，改为贴近实际的应用场景"></textarea></label><button class="button secondary" :disabled="busy" @click="generateRevision"><Sparkles :size="16" />{{ busy?'正在生成候选…':'生成修改候选' }}</button>
            <template v-if="dialog.candidate"><BankQuestionPreview :item="{...selected,question:dialog.candidate.question}" :materials="bank.materials" show-answer /><button class="button primary" :disabled="busy" @click="adoptRevision">采纳到草稿，重新核对</button></template></div>
          <div v-else-if="dialog.mode==='move'" class="stack"><label>目标章节<select v-model="dialog.section_id"><option :value="null">未分类</option><option v-for="s in chapters" :key="s.id" :value="s.id">{{ '　'.repeat(s.depth) }}{{ s.title }}</option></select></label><button class="button primary" :disabled="busy" @click="bulk('move',checked,{section_id:dialog.section_id})">移动所选题目</button></div>
          <div v-else-if="dialog.mode==='tags'" class="stack"><label>新标签<input v-model="dialog.tags" placeholder="用逗号分隔"></label><button class="button primary" :disabled="busy" @click="bulk('tags',checked,{tags:dialog.tags.split(/[,，、]/).map(t=>t.trim()).filter(Boolean)})">设置标签</button></div>
          <div v-else-if="dialog.mode==='delete'" class="stack"><p>删除所选 {{ checked.length }} 道草稿题目？已发布版本保持原内容。</p><button class="button primary" :disabled="busy" @click="bulk('delete')">确认删除</button></div>
          <p v-if="dialog?.error" class="error" role="alert">{{ dialog.error }}</p>
        </template>
      </Modal>
    </template>
  </div>
</template>
