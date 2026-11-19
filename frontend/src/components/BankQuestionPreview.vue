<script setup>
import { computed, ref } from 'vue'
import { bankKinds, docText } from '../questionBanks'
import BankRichContent from './BankRichContent.vue'
import MathPreview from './MathPreview.vue'
const props = defineProps({ item: Object, materials: { type: Array, default: () => [] }, number: Number, showAnswer: Boolean })
const expanded = ref(props.showAnswer)
const question = computed(() => props.item.question)
const material = computed(() => props.materials.find((m) => m.id === question.value.material_id))
const letters = computed(() => question.value.options.filter((o) => question.value.answer.correct_options.includes(o.id)).map((o) => String.fromCharCode(65 + question.value.options.indexOf(o))).join('、'))
</script>
<template>
  <article class="bank-preview-question">
    <header class="section-heading"><strong>{{ number ? number + '. ' : '' }}{{ bankKinds[question.kind] }}</strong><span class="bank-chip">{{ question.difficulty }}</span></header>
    <div v-if="material" class="bank-material-context"><strong>{{ material.title }}</strong><BankRichContent :value="material.body" /></div>
    <BankRichContent :value="question.body" />
    <div v-if="['single','multiple'].includes(question.kind)" class="bank-preview-options"><label v-for="(option,index) in question.options" :key="option.id"><input :type="question.kind === 'single' ? 'radio' : 'checkbox'" :name="'preview-'+item.id"><span>{{ String.fromCharCode(65+index) }}.</span><BankRichContent :value="option.body" /></label></div>
    <div v-else-if="question.kind === 'judge'" class="actions"><label class="bank-check"><input type="radio" :name="'preview-'+item.id">正确</label><label class="bank-check"><input type="radio" :name="'preview-'+item.id">错误</label></div>
    <div v-else-if="question.kind === 'blank'" class="bank-fields"><label v-for="(blank,index) in question.answer.blanks" :key="blank.id">第 {{ index+1 }} 空<input placeholder="输入你的答案"></label></div>
    <textarea v-else rows="4" aria-label="练习作答" placeholder="在此尝试作答…"></textarea>
    <div class="actions"><button class="button secondary" @click="expanded = true">提交本题并查看答案</button><button class="button subtle" :aria-expanded="expanded" @click="expanded = !expanded">{{ expanded ? '收起答案' : '查看参考答案' }}</button></div>
    <div v-if="expanded" class="bank-answer-panel stack"><strong>参考答案</strong><p v-if="['single','multiple'].includes(question.kind)">{{ letters || '待补充' }}</p>
      <p v-else-if="question.kind === 'judge'">{{ question.answer.judgment === null ? '待补充' : question.answer.judgment ? '正确' : '错误' }}</p>
      <ol v-else-if="question.kind === 'blank'"><li v-for="blank in question.answer.blanks" :key="blank.id"><MathPreview :source="blank.answers.join(' / ')" /></li></ol>
      <BankRichContent v-else :value="question.answer.body" />
      <template v-if="docText(question.answer.explanation).trim()"><strong>解析</strong><BankRichContent :value="question.answer.explanation" /></template>
      <p v-for="(source,i) in item.source_labels || []" :key="i" class="muted">参考：{{ source.title }} · {{ source.start }}{{ source.end !== source.start ? '–'+source.end : '' }} 页</p>
    </div>
  </article>
</template>
