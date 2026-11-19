<script>
import { defineComponent, h } from 'vue'
import { imageUrl } from '../questionBanks'
import { renderFormula } from '../examMath'

export default defineComponent({
  props: { value: Object },
  setup(props) {
    function render(node) {
      if (!node) return null
      if (node.type === 'text') {
        let result = node.text
        for (const mark of node.marks || []) {
          const tag = { bold: 'strong', italic: 'em', underline: 'u', strike: 's', code: 'code', link: 'a' }[mark.type]
          if (tag) result = h(tag, mark.type === 'link' && /^https?:\/\//i.test(mark.attrs?.href || '')
            ? { href: mark.attrs.href, target: '_blank', rel: 'noopener noreferrer nofollow' } : {}, result)
        }
        return result
      }
      if (node.type === 'formula') {
        try { return h('span', { class: ['bank-formula', { 'bank-formula-display': node.attrs?.display }], innerHTML: renderFormula(node.attrs.latex, !!node.attrs.display) }) }
        catch { return h('span', { class: 'bank-formula-error' }, node.attrs?.latex) }
      }
      if (node.type === 'image') return h('img', { src: imageUrl(node.attrs.assetId), alt: node.attrs.alt || '题目插图', loading: 'lazy' })
      const tags = { doc: 'div', paragraph: 'p', heading: 'h' + (node.attrs?.level || 2), blockquote: 'blockquote', bulletList: 'ul', orderedList: 'ol', listItem: 'li',
        codeBlock: 'pre', table: 'table', tableRow: 'tr', tableCell: 'td', tableHeader: 'th', horizontalRule: 'hr', hardBreak: 'br' }
      const attributes = {}
      if (['tableCell', 'tableHeader'].includes(node.type)) Object.assign(attributes, { colspan: node.attrs?.colspan || 1, rowspan: node.attrs?.rowspan || 1 })
      if (node.type === 'orderedList') attributes.start = node.attrs?.start || 1
      const children = (node.content || []).map(render)
      return h(tags[node.type] || 'span', attributes, node.type === 'codeBlock' ? [h('code', {}, children)] : children)
    }
    return () => h('div', { class: 'bank-prose' }, props.value?.type === 'doc' ? props.value.content?.map(render) : [])
  },
})
</script>
