import katex from 'katex'
import 'katex/dist/katex.min.css'

export const MATH_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
const WORD_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
const PACKAGE_NS = 'http://schemas.microsoft.com/office/2006/xmlPackage'
const mathPattern = /(?<!\\)\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<![\\$])\$([^\n\r$]+?)(?<!\\)\$(?!\$)/g

export function renderFormula(value, displayMode = false) {
  if (!value?.trim()) return ''
  return katex.renderToString(value, { displayMode, trust: false, throwOnError: true, maxSize: 16, maxExpand: 500 })
}

export function mathSegments(value = '') {
  const segments = []
  let start = 0
  for (const match of value.matchAll(mathPattern)) {
    if (start < match.index) segments.push({ text: value.slice(start, match.index), math: false })
    const index = match.slice(1).findIndex((entry) => entry !== undefined)
    segments.push({ text: match[index + 1], math: true, display: index < 2, original: match[0] })
    start = match.index + match[0].length
  }
  if (start < value.length) segments.push({ text: value.slice(start), math: false })
  return segments
}

export function equationPackage(omml) {
  return '<pkg:package xmlns:pkg="' + PACKAGE_NS + '"><pkg:part pkg:name="/word/document.xml" ' +
    'pkg:contentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml">' +
    '<pkg:xmlData><w:document xmlns:w="' + WORD_NS + '"><w:body><w:p>' +
    omml + '</w:p></w:body></w:document></pkg:xmlData></pkg:part></pkg:package>'
}

export function equationMarkup(source) {
  const attribute = source?.attributes?.find((item) =>
    ['latex', 'projection'].includes(item.localName) && item.namespaceUri === 'urn:dianoia:math')
  if (attribute?.value) return attribute.value
  const prefix = 'DianoiaMath_'
  const findMarker = (node) => {
    if (node.localName === 'rStyle' && node.namespaceUri === WORD_NS) {
      const value = node.attributes.find((item) => item.localName === 'val')?.value
      if (value?.startsWith(prefix)) return value.slice(prefix.length)
    }
    for (const child of node.children || []) {
      const result = findMarker(child)
      if (result) return result
    }
    return ''
  }
  const marker = source ? findMarker(source) : ''
  try {
    return marker ? new TextDecoder().decode(Uint8Array.from(atob(marker.replaceAll('-', '+').replaceAll('_', '/')), (c) => c.charCodeAt(0))) : ''
  } catch { return '' }
}
