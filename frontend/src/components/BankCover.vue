<script setup>
import { computed } from 'vue'
import { imageUrl } from '../questionBanks'
const props = defineProps({ bank: { type: Object, required: true }, course: { type: String, default: '' }, thumbnail: Boolean })
const palettes = { academic: ['#f2eee7','#252333'], blue: ['#eaf2ff','#153568'], paper: ['#f5e8d9','#50372c'], nature: ['#e7f2ec','#173e35'], purple: ['#eeebfc','#352561'], grid: ['#172433','#f0f4ff'] }
const colors = computed(() => palettes[props.bank.cover?.theme] || palettes.academic)
const accent = computed(() => props.bank.cover?.accent || '#7759ce')
const lines = computed(() => {
  const text = props.bank.title || '未命名题库'
  return Array.from({ length: Math.min(3, Math.ceil(text.length / 17)) }, (_, i) => text.slice(i * 17, i * 17 + 17) + (i === 2 && text.length > 51 ? '…' : ''))
})
</script>
<template>
  <img v-if="bank.cover?.asset_id" class="bank-cover" :src="imageUrl(bank.cover.asset_id)+(thumbnail?'?thumbnail=true':'')" :alt="bank.title + '封面'" loading="lazy">
  <svg v-else class="bank-cover" viewBox="0 0 1200 675" role="img" :aria-label="bank.title + '封面'">
    <rect width="1200" height="675" :fill="colors[0]" />
    <g :fill="accent" :stroke="accent">
      <template v-if="bank.cover?.theme === 'blue'"><path d="M750 675L1200 200v475zM920 0h280v280z" opacity=".18" /><circle cx="1110" cy="155" r="95" opacity=".22" /></template>
      <template v-else-if="bank.cover?.theme === 'paper'"><rect x="880" y="130" width="255" height="440" rx="15" opacity=".12" transform="rotate(12 1000 300)" /><path d="M930 230h140m-140 35h140m-140 35h90" stroke-width="5" /></template>
      <template v-else-if="bank.cover?.theme === 'nature'"><ellipse cx="1090" cy="185" rx="145" ry="260" opacity=".15" transform="rotate(-36 1090 185)" /><ellipse cx="980" cy="570" rx="170" ry="240" opacity=".16" /></template>
      <template v-else-if="bank.cover?.theme === 'purple'"><circle cx="1090" cy="80" r="220" opacity=".18" /><rect x="840" y="390" width="330" height="330" rx="70" opacity=".2" transform="rotate(24 1000 500)" /></template>
      <template v-else-if="bank.cover?.theme === 'grid'"><path v-for="i in 22" :key="i" :d="`M${i*55} 0v675 M0 ${i*55}h1200`" fill="none" opacity=".12" /><circle cx="1060" cy="260" r="200" fill="none" opacity=".3" stroke-width="2" /></template>
      <template v-else><path d="M875 0h325v675H875z" opacity=".12" /><circle cx="1080" cy="160" r="230" fill="none" stroke-width="2" /><path d="M895 400h175m-175 30h125" stroke-width="12" /></template>
    </g>
    <g font-family="Microsoft YaHei,PingFang SC,sans-serif" :text-anchor="bank.cover?.layout === 'center' ? 'middle' : 'start'">
      <text :x="bank.cover?.layout === 'center' ? 600 : 85" y="106" :fill="accent" font-size="22" letter-spacing="3">DIANOIA · 自主练习</text>
      <text :x="bank.cover?.layout === 'center' ? 600 : 85" :y="lines.length < 3 ? 280 : 230" :fill="colors[1]" font-size="59" font-weight="700"><tspan v-for="(line,i) in lines" :key="i" :x="bank.cover?.layout === 'center' ? 600 : 85" :dy="i ? 77 : 0">{{ line }}</tspan></text>
      <text :x="bank.cover?.layout === 'center' ? 600 : 85" y="585" :fill="colors[1]" opacity=".6" font-size="25">{{ course.slice(0,36) }}</text>
    </g>
  </svg>
</template>
