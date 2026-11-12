<script setup>
import { ChevronRight, Plus, X } from 'lucide-vue-next'
const props = defineProps({ nodes: { type: Array, required: true }, editing: Boolean, max: Number, depth: { type: Number, default: 1 } })
const emit = defineEmits(['jump'])
function addChild(node) {
  node.children.push({ title: '', start: node.start, end: node.end, children: [] })
}
</script>

<template>
  <ul class="outline-tree">
    <li v-for="(node, index) in nodes" :key="index">
      <div v-if="editing" class="outline-fields">
        <input v-model="node.title" aria-label="章节名称" placeholder="章节名称" maxlength="160" required>
        <div class="actions">
          <input v-model.number="node.start" aria-label="开始页" type="number" min="1" :max="max" required><span>–</span>
          <input v-model.number="node.end" aria-label="结束页" type="number" min="1" :max="max" required>
          <button v-if="depth < 8" type="button" class="button subtle icon-only" aria-label="添加子章节" @click="addChild(node)"><Plus :size="14" /></button>
          <button type="button" class="button subtle icon-only" aria-label="删除章节" @click="props.nodes.splice(index, 1)"><X :size="14" /></button>
        </div>
      </div>
      <button v-else class="outline-link" @click="emit('jump', node.start)"><ChevronRight :size="13" /><span>{{ node.title }}</span><small>{{ node.start }}</small></button>
      <ResourceOutline v-if="node.children.length" :nodes="node.children" :editing="editing" :max="max" :depth="depth + 1" @jump="emit('jump', $event)" />
    </li>
  </ul>
</template>
