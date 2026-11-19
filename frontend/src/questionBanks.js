import { Node, Extension } from '@tiptap/core'
import { renderFormula, mathSegments } from './examMath'

export const bankKinds = { single: '单项选择题', multiple: '多项选择题', judge: '判断题', blank: '填空题', written: '解答题' }
export const bankStatuses = { draft: '草稿', published: '已发布', offline: '已下架', archived: '已归档' }
export const uid = () => crypto.randomUUID().replaceAll('-', '')
export const clone = (data) => JSON.parse(JSON.stringify(data))
export const emptyDoc = () => ({ type: 'doc', content: [{ type: 'paragraph' }] })
export function textDoc(text = '') {
  return { type: 'doc', content: text.split('\n').map((line) => ({ type: 'paragraph', content: mathSegments(line).map((part) => part.math
    ? { type: 'formula', attrs: { latex: part.text, display: part.display } } : { type: 'text', text: part.text }).filter((part) => part.type !== 'text' || part.text) })) }
}
export const docText = (node) => node?.type === 'text' ? node.text : node?.type === 'formula' ? node.attrs.latex
  : node?.type === 'image' ? '[图片]' : (node?.content || []).map(docText).join(node?.type === 'paragraph' ? '' : '\n')
export const freshQuestion = (sectionId = null) => ({ kind: 'single', body: emptyDoc(), options: Array.from({ length: 4 }, () => ({ id: uid(), body: emptyDoc() })),
  answer: { body: emptyDoc(), explanation: emptyDoc(), correct_options: [], judgment: null, blanks: [] },
  section_id: sectionId, material_id: null, tags: [], difficulty: '适中', sources: [], confirmed: false, included: true })
export function sectionsFlat(sections, parent = null, depth = 0) {
  return sections.filter((s) => s.parent_id === parent).flatMap((s) => [{ ...s, depth }, ...sectionsFlat(sections, s.id, depth + 1)])
}
export const imageUrl = (id) => `/api/question-banks/assets/${encodeURIComponent(id)}`

export function paragraphAfterTable(editor) {
  const { $from } = editor.state.selection
  for (let depth = $from.depth; depth > 0; depth--) {
    if ($from.node(depth).type.name === 'table') {
      const position = $from.after(depth)
      if (editor.state.doc.nodeAt(position)?.type.name === 'paragraph') return editor.chain().focus().setTextSelection(position + 1).run()
      return editor.chain().insertContentAt(position, { type: 'paragraph' }).setTextSelection(position + 1).focus().run()
    }
  }
  return editor.chain().focus('end').insertContent({ type: 'paragraph' }).run()
}

export const BankShortcuts = Extension.create({
  name: 'bankShortcuts',
  addKeyboardShortcuts() { return {
    'Mod-m': () => { this.editor.view.dom.dispatchEvent(new CustomEvent('bank-open-formula', { bubbles: true })); return true },
    'Mod-Enter': () => paragraphAfterTable(this.editor),
  } },
})

export const FormulaNode = Node.create({
  name: 'formula', group: 'inline', inline: true, atom: true,
  addAttributes() { return { latex: { default: '' }, display: { default: false } } },
  parseHTML() { return [{ tag: 'span[data-bank-formula]', getAttrs: (el) => ({ latex: el.getAttribute('data-bank-formula'), display: el.getAttribute('data-display') === 'true' }) }] },
  renderHTML({ node }) { return ['span', { 'data-bank-formula': node.attrs.latex, 'data-display': node.attrs.display ? 'true' : 'false' }, node.attrs.latex] },
  addNodeView() { return ({ node, getPos, editor }) => {
    const dom = document.createElement('span')
    const draw = (item) => {
      dom.className = 'bank-formula' + (item.attrs.display ? ' bank-formula-display' : '')
      dom.contentEditable = 'false'
      dom.setAttribute('title', '双击编辑公式 · Ctrl/⌘+M 插入公式')
      try { dom.innerHTML = renderFormula(item.attrs.latex, item.attrs.display) }
      catch { dom.textContent = item.attrs.latex; dom.classList.add('bank-formula-error') }
    }
    draw(node)
    dom.addEventListener('dblclick', (event) => { event.preventDefault(); if (editor.isEditable) dom.dispatchEvent(new CustomEvent('bank-edit-formula', {
      bubbles: true, detail: { position: getPos(), latex: node.attrs.latex, display: node.attrs.display },
    })) })
    return { dom, update: (next) => { if (next.type.name !== 'formula') return false; node = next; draw(node); return true } }
  } },
})

export const BankImage = Node.create({
  name: 'image', group: 'block', atom: true, draggable: true,
  addAttributes() { return { assetId: { default: '' }, alt: { default: '' }, title: { default: null } } },
  parseHTML() { return [{ tag: 'img[data-bank-asset]', getAttrs: (el) => ({ assetId: el.getAttribute('data-bank-asset'), alt: el.getAttribute('alt') || '', title: el.getAttribute('title') }) }] },
  renderHTML({ node }) { return ['img', { 'data-bank-asset': node.attrs.assetId, src: imageUrl(node.attrs.assetId), alt: node.attrs.alt, title: node.attrs.title }] },
})
