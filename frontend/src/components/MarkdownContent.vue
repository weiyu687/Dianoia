<script setup>
import { computed } from 'vue'
import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  text: { type: String, default: '' },
})

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: true,
})

const defaultLinkOpen = markdown.renderer.rules.link_open
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const targetIndex = tokens[index].attrIndex('target')
  if (targetIndex < 0) tokens[index].attrPush(['target', '_blank'])
  else tokens[index].attrs[targetIndex][1] = '_blank'
  const relIndex = tokens[index].attrIndex('rel')
  if (relIndex < 0) tokens[index].attrPush(['rel', 'noreferrer noopener'])
  else tokens[index].attrs[relIndex][1] = 'noreferrer noopener'
  return defaultLinkOpen
    ? defaultLinkOpen(tokens, index, options, env, self)
    : self.renderToken(tokens, index, options)
}

const html = computed(() => DOMPurify.sanitize(markdown.render(props.text), {
  USE_PROFILES: { html: true },
  FORBID_TAGS: ['iframe', 'object', 'embed', 'form', 'input', 'button'],
}))
</script>

<template>
  <div class="markdown-content" v-html="html"></div>
</template>
