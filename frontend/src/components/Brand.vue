<script setup>
import { Aperture } from 'lucide-vue-next'
defineProps({ subtitle: String })
</script>

<template>
  <div class="brand">
    <span class="brand-mark"><Aperture :size="22" :stroke-width="2.2" /></span>
    <div><strong>Dianoia</strong><small v-if="subtitle">{{ subtitle }}</small></div>
  </div>
</template>
