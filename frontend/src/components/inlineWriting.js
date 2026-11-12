import { Extension } from '@tiptap/core'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'

export const suggestionKey = new PluginKey('writing-suggestion')

export const InlineWriting = Extension.create({
  name: 'inlineWriting',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: suggestionKey,
      state: {
        init: () => null,
        apply(transaction, previous) {
          const value = transaction.getMeta(suggestionKey)
          if (value !== undefined) return value
          if (transaction.docChanged || transaction.selectionSet) return null
          return previous
        },
      },
      props: {
        decorations(state) {
          const item = suggestionKey.getState(state)
          if (!item) return null
          const widget = Decoration.widget(item.position, () => {
            const node = document.createElement('span')
            node.className = 'writing-ghost'
            node.contentEditable = 'false'
            node.textContent = item.text
            node.setAttribute('aria-hidden', 'true')
            return node
          }, { side: 1, key: `suggestion-${item.id}` })
          return DecorationSet.create(state.doc, [widget])
        },
      },
    })]
  },
})
