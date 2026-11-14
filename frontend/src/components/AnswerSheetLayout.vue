<script setup>
import { computed } from 'vue'
import { examKinds } from '../examKinds'

const props = defineProps({ state: { type: Object, required: true }, disabled: Boolean })
const emit = defineEmits(['build'])
const areas = Object.fromEntries(props.state.questions.map((q) => [q.id, { ...q.area }]))
const groups = computed(() => {
  const result = new Map()
  for (const question of props.state.questions) {
    if (!result.has(question.group)) result.set(question.group, [])
    result.get(question.group).push(question)
  }
  return result
})

function submit() {
  if (props.state.edited && !window.confirm('重新生成会替换手动编辑的答题卡正文，是否继续？')) return
  emit('build', { areas, replace_edits: props.state.edited })
}
</script>

<template>
  <form v-if="state.can_build" id="answer-sheet-layout" class="stack" @submit.prevent="submit">
    <p v-if="state.edited" class="muted">生成会根据作答区设置重排答题卡，并替换 Word 中的手动修改。</p>
    <fieldset v-for="[group, questions] of groups" :key="group" class="sheet-layout-group" :disabled="disabled">
      <legend>第 {{ group }} 大题 · {{ examKinds[questions[0].kind] }}</legend>
      <div v-for="q in questions" :key="q.id" class="sheet-layout-row">
        <div class="sheet-question"><strong>{{ q.number }}.</strong><span>{{ q.stem }}</span></div>
        <div class="sheet-area-fields">
          <template v-if="['single','multiple'].includes(q.kind)">
            <span v-if="q.option_count >= 2">{{ q.option_count }} 个选项</span>
            <label v-else>选项数量<input v-model.number="areas[q.id].option_count" type="number" min="2" max="8" required></label>
          </template>
          <span v-else-if="q.kind === 'judge'">√ / ×</span>
          <template v-else-if="q.kind === 'blank'">
            <label>空格数<input v-model.number="areas[q.id].blanks" type="number" min="1" max="10" required></label>
            <label>每空长度（mm）<input v-model.number="areas[q.id].blank_mm" type="number" min="12" max="115" required></label>
            <label>样式<select v-model="areas[q.id].style"><option value="ruled">下划线</option><option value="blank">留空</option></select></label>
          </template>
          <template v-else>
            <label>样式<select v-model="areas[q.id].style"><option value="ruled">横线</option><option value="boxed">边框</option><option value="blank">留空</option></select></label>
            <label>行数<input v-model.number="areas[q.id].lines" type="number" min="1" max="20" required></label>
            <label>每行高度（mm）<input v-model.number="areas[q.id].line_mm" type="number" min="6" max="15" required></label>
            <label>作答区宽度（mm）<input v-model.number="areas[q.id].width_mm" type="number" min="30" max="146" required></label>
          </template>
        </div>
      </div>
    </fieldset>
  </form>
  <p v-else>请先在试卷正文标记并确认全部题目，补齐空题位。答题卡最多支持 200 道题。</p>
</template>
