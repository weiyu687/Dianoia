// Tiptap uses findLast in its transaction dispatcher. Keep the editor usable
// on older school-managed Chromium installations.
if (!Array.prototype.findLast) {
  Object.defineProperty(Array.prototype, 'findLast', {
    configurable: true,
    writable: true,
    value(predicate, receiver) {
      if (this == null || typeof predicate !== 'function') throw new TypeError('Invalid findLast arguments')
      const values = Object(this)
      for (let index = values.length - 1; index >= 0; index--) {
        if (predicate.call(receiver, values[index], index, values)) return values[index]
      }
      return undefined
    },
  })
}
