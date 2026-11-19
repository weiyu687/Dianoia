<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Plus, Save, Sigma, Sparkles, Trash2 } from 'lucide-vue-next'
import { bankKinds, clone, emptyDoc, freshQuestion, sectionsFlat, uid } from '../questionBanks'
import BankRichEditor from './BankRichEditor.vue'
import BankRichContent from './BankRichContent.vue'
import MapSources from './MapSources.vue'
import FormulaEditor from './FormulaEditor.vue'
import Modal from './Modal.vue'

const props = defineProps({ value: { type: Object, required: true }, bank: { type: Object, required: true }, resources: Array, busy: Boolean, error: String })
const emit = defineEmits(['save', 'dirty', 'revise'])
const question = ref(clone(props.value.question))
const tagText = ref(question.value.tags.join('，'))
const blankFormula = ref(null)
let resetting = false
watch(() => props.value, async (value) => {
  resetting = true
  question.value = clone(value.question)
  tagText.value = question.value.tags.join('，')
  await nextTick(); resetting = false
}, { deep: true })
watch(() => JSON.stringify({ ...question.value, confirmed: undefined }), () => {
  if (!resetting) { question.value.confirmed = false; emit('dirty', true) }
})
watch(() => question.value.confirmed, () => { if (!resetting) emit('dirty', true) })
const chapters = computed(() => sectionsFlat(props.bank.sections))
const currentMaterial = computed(() => props.bank.materials.find((m) => m.id === question.value.material_id))
function kindChange() {
  const replacement = freshQuestion(question.value.section_id)
  question.value.options = ['single','multiple'].includes(question.value.kind) ? replacement.options : []
  question.value.answer = { body: emptyDoc(), explanation: question.value.answer.explanation, correct_options: [], judgment: null,
    blanks: question.value.kind === 'blank' ? [{ id: uid(), answers: [] }] : [] }
}
function removeOption(id) {
  question.value.options = question.value.options.filter((o) => o.id !== id)
  question.value.answer.correct_options = question.value.answer.correct_options.filter((key) => key !== id)
}
function choose(id, checked) {
  question.value.answer.correct_options = question.value.kind === 'single' ? [id] : checked
    ? [...question.value.answer.correct_options, id] : question.value.answer.correct_options.filter((key) => key !== id)
}
function save(confirm = false) {
  const item = clone(question.value)
  item.tags = tagText.value.split(/[,，、]/).map((t) => t.trim()).filter(Boolean)
  if (item.kind !== 'written') item.answer.body = emptyDoc()
  item.confirmed = confirm || item.confirmed
  emit('save', item)
}
defineExpose({ save })
</script>

<template>
  <div class="bank-question-form stack" @keydown.ctrl.s.prevent="save()" @keydown.meta.s.prevent="save()">
    <div class="bank-question-heading"><div><span class="bank-eyebrow">QUESTION EDITOR</span><h2>{{ value.id ? '编辑题目' : '新建题目' }}</h2></div>
      <button v-if="value.id" class="button secondary" :disabled="busy" @click="emit('revise')"><Sparkles :size="16" /> AI 修改本题</button></div>
    <div class="bank-fields three"><label>题型<select v-model="question.kind" aria-label="题型" @change="kindChange"><option v-for="(name,key) in bankKinds" :key="key" :value="key">{{ name }}</option></select></label>
      <label>所属章节<select v-model="question.section_id" aria-label="所属章节"><option :value="null">未分类</option><option v-for="s in chapters" :key="s.id" :value="s.id">{{ '　'.repeat(s.depth) }}{{ s.title }}</option></select></label>
      <label>预设难度<select v-model="question.difficulty" aria-label="预设难度"><option>基础</option><option>适中</option><option>较难</option></select></label></div>
    <label>共享材料<select v-model="question.material_id" aria-label="共享材料"><option :value="null">无共用材料</option><option v-for="m in bank.materials" :key="m.id" :value="m.id">{{ m.title }}</option></select></label>
    <details v-if="currentMaterial" class="bank-material-context"><summary>{{ currentMaterial.title }}</summary><BankRichContent :value="currentMaterial.body" /></details>
    <div class="stack"><strong>题干</strong><BankRichEditor v-model="question.body" :bank-id="bank.id" label="题干" /></div>
    <div v-if="['single','multiple'].includes(question.kind)" class="stack">
      <div class="section-heading"><strong>选项与正确答案</strong><button class="button subtle" :disabled="question.options.length >= 8" @click="question.options.push({ id: uid(), body: emptyDoc() })"><Plus :size="15" /> 添加选项</button></div>
      <div v-for="(option,index) in question.options" :key="option.id" class="bank-option-edit">
        <label class="bank-option-key" :title="'设为正确选项 ' + String.fromCharCode(65+index)"><input :type="question.kind === 'single' ? 'radio' : 'checkbox'" name="correct-option"
          :checked="question.answer.correct_options.includes(option.id)" :aria-label="'正确选项 ' + String.fromCharCode(65+index)" @change="choose(option.id, $event.target.checked)">{{ String.fromCharCode(65+index) }}</label>
        <BankRichEditor v-model="option.body" :bank-id="bank.id" :label="String.fromCharCode(65+index) + '选项'" compact />
        <button class="button subtle icon-only" :aria-label="'删除选项 ' + String.fromCharCode(65+index)" :disabled="question.options.length <= 2" @click="removeOption(option.id)"><Trash2 :size="16" /></button>
      </div><p class="muted">勾选正确答案。选项使用独立标识保存，编辑文字不会改变答案对应关系。</p>
    </div>
    <div v-else-if="question.kind === 'judge'" class="stack"><strong>参考答案</strong><div class="actions">
      <label class="bank-check"><input v-model="question.answer.judgment" type="radio" :value="true" name="judgment">正确</label>
      <label class="bank-check"><input v-model="question.answer.judgment" type="radio" :value="false" name="judgment">错误</label></div></div>
    <div v-else-if="question.kind === 'blank'" class="stack"><div class="section-heading"><strong>空位与参考答案</strong><button class="button subtle" :disabled="question.answer.blanks.length >= 20" @click="question.answer.blanks.push({ id: uid(), answers: [] })"><Plus :size="15" /> 添加空位</button></div>
      <div v-for="(blank,index) in question.answer.blanks" :key="blank.id" class="bank-blank-edit"><label>第 {{ index+1 }} 空<input :value="blank.answers.join('；')" placeholder="多个参考表达用分号隔开" maxlength="12000" @change="blank.answers = $event.target.value.split(/[;；]/).map(t => t.trim()).filter(Boolean)"></label>
        <button class="button secondary icon-only" :aria-label="'第'+(index+1)+'空公式答案'" title="用公式编辑首个参考表达" @click="blankFormula={id:blank.id,latex:(blank.answers[0]||'').replace(/^\\\(|\\\)$/g,'')}"><Sigma :size="17" /></button>
        <button class="button subtle icon-only" aria-label="移除此空位" @click="question.answer.blanks.splice(index,1)"><Trash2 :size="16" /></button></div>
      <p class="muted">在题干中标注对应的空位序号。这里保存参考表达，不设置评分规则。</p></div>
    <div v-else class="stack"><strong>参考答案</strong><BankRichEditor v-model="question.answer.body" :bank-id="bank.id" label="参考答案" /></div>
    <div class="stack"><strong>解析与解题过程</strong><BankRichEditor v-model="question.answer.explanation" :bank-id="bank.id" label="解析" /></div>
    <label>知识点与专业标签<input v-model="tagText" placeholder="例如：函数，编程，参数传递" maxlength="490" @input="question.confirmed = false; emit('dirty', true)"></label>
    <details class="bank-source-details"><summary>本题参考资料 · {{ question.sources.length }} 项</summary><MapSources v-model="question.sources" :resources="resources || []" /></details>
    <div class="bank-form-footer"><div class="actions"><label class="bank-check"><input v-model="question.included" type="checkbox">参与发布</label>
      <label class="bank-check"><input v-model="question.confirmed" type="checkbox">已核对题目与答案</label></div>
      <div class="actions"><button class="button secondary" :disabled="busy" @click="save()"><Save :size="16" /> 保存草稿</button>
        <button class="button primary" :disabled="busy" @click="save(true)"><Check :size="16" />{{ busy ? '正在保存…' : '保存并确认' }}</button></div></div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <Modal :open="!!blankFormula" title="填空参考答案公式" wide @close="blankFormula=null"><FormulaEditor v-if="blankFormula" :initial="blankFormula.latex" @apply="latex=>{const blank=question.answer.blanks.find(b=>b.id===blankFormula.id);if(blank)blank.answers=[`\\(${latex}\\)`,...blank.answers.slice(1)];blankFormula=null}" /></Modal>
  </div>
</template>
