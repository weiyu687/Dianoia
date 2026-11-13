import MindMap from 'simple-mind-map'
import Drag from 'simple-mind-map/src/plugins/Drag.js'
import Export from 'simple-mind-map/src/plugins/Export.js'
import KeyboardNavigation from 'simple-mind-map/src/plugins/KeyboardNavigation.js'
import AssociativeLine from 'simple-mind-map/src/plugins/AssociativeLine.js'
import OuterFrame from 'simple-mind-map/src/plugins/OuterFrame.js'

MindMap.usePlugin(Drag).usePlugin(Export).usePlugin(KeyboardNavigation).usePlugin(AssociativeLine).usePlugin(OuterFrame)
MindMap.extendNodeDataNoStylePropList([
  'mapNote', 'mapSources', 'mapLabels', 'mapNodeLinks', 'mapFormula', 'mapTable', 'mapCode', 'mapHyperlinkLabel',
])

export const palettes = {
  indigo: { label: '鸢尾紫', root: '#5742a6', fill: '#ede9fb', border: '#b6a8e6', paper: '#faf8ff' },
  ocean: { label: '深海蓝', root: '#176a84', fill: '#e4f4f8', border: '#81c2d3', paper: '#f4fcfe' },
  forest: { label: '松林绿', root: '#24654b', fill: '#e6f4e9', border: '#98c7a8', paper: '#f6fcf6' },
  coral: { label: '珊瑚橙', root: '#a54a39', fill: '#fcece5', border: '#e3ab9b', paper: '#fff8f4' },
  slate: { label: '岩灰', root: '#3c4d62', fill: '#eaf0f5', border: '#acbdcd', paper: '#f7fafc' },
}

export const layouts = {
  mindMap: '双向导图',
  logicalStructure: '向右逻辑图',
  organizationStructure: '组织结构图',
}

export const mapFontFamily = 'Microsoft YaHei UI, PingFang SC, Noto Sans CJK SC, sans-serif'
const styleKeys = ['fillColor', 'color', 'borderColor', 'lineColor', 'fontSize', 'fontWeight', 'shape']

function escapeSvgText(value = '') {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
}

export function canvasTheme(palette, dark = false) {
  const { root, fill, border, paper } = palettes[palette]
  const node = { fontFamily: mapFontFamily, shape: 'roundedRectangle', borderWidth: 1 }
  return {
    backgroundColor: dark ? '#1d1d26' : paper,
    associativeLineColor: dark ? border : root,
    associativeLineTextColor: dark ? '#f1f0f6' : '#302b3e',
    lineColor: dark ? border : root, lineWidth: 1.5, lineRadius: 9, paddingY: 8, paddingX: 13,
    root: { ...node, fillColor: root, color: '#ffffff', borderColor: root, fontSize: 21 },
    second: { ...node, fillColor: fill, color: '#231d34', borderColor: border, fontSize: 16, fontWeight: 'bold', marginX: 56, marginY: 20 },
    node: { ...node, fillColor: '#ffffff', color: '#262331', borderColor: border, fontSize: 14, marginX: 34, marginY: 12 },
  }
}

const sourceColors = ['#6745aa', '#176d69', '#a34525', '#28598e', '#8d3f65', '#4e682d', '#825023', '#47546e']
export const labelBadges = (node) => (node.labels || []).map((text) => ({
  text, style: { fill: '#465574', height: 18, fontSize: 11, paddingX: 5 }, kind: 'label',
}))

export function mapSourceNumbers(map) {
  const ids = new Set(map.sources.map((source) => source.resource_id))
  for (const { node } of flatNodes(map.root)) {
    for (const source of node.sources) ids.add(source.resource_id)
  }
  return new Map([...ids].map((id, index) => [id, index + 1]))
}

export function sourceColor(number) {
  return sourceColors[(number - 1) % sourceColors.length]
}

export function mapNodeLinks(map, id) {
  return [...new Set(flatNodes(map.root).flatMap(({ node }) => {
    if (node.id === id) return node.node_links || []
    return node.node_links?.includes(id) ? [node.id] : []
  }))]
}

export function editorBadges(map) {
  const numbers = mapSourceNumbers(map)
  const entries = flatNodes(map.root)
  const ids = new Set(entries.map(({ node }) => node.id))
  const linked = new Set()
  for (const { node } of entries) {
    for (const target of node.node_links || []) {
      if (ids.has(target)) {
        linked.add(node.id)
        linked.add(target)
      }
    }
  }
  return (node) => {
    const ids = [...new Set(node.sources.map((source) => source.resource_id))]
    return [
      ...labelBadges(node),
      ...(node.note ? [{ text: '备注', style: { fill: '#9b4635' }, kind: 'note' }] : []),
      ...ids.sort((a, b) => numbers.get(a) - numbers.get(b)).map((id) => ({
        text: `资料 ${numbers.get(id)}`, kind: 'source', resourceId: id, style: { fill: sourceColor(numbers.get(id)) },
      })),
      ...(linked.has(node.id) ? [{ text: '双向链接', kind: 'nodeLinks', style: { fill: '#4c617c' } }] : []),
      ...[['formula', '公式'], ['table', '表格'], ['code', '代码块']].flatMap(([kind, text]) =>
        node[kind] ? [{ text, kind, style: { fill: '#4c617c' } }] : []),
    ]
  }
}

export function toCanvas(node, full = false, badges = labelBadges) {
  const lines = node.lines || []
  const hasAnchors = lines.some((line) => line.anchors)
  const hasOffsets = lines.every((line) => line.offsets)
  return {
    data: {
      uid: node.id, text: node.text, expand: full || node.expanded, dir: node.direction || undefined,
      ...node.style, mapNote: node.note, mapSources: node.sources,
      tag: badges(node),
      mapLabels: node.labels, mapNodeLinks: node.node_links, mapFormula: node.formula, mapTable: node.table, mapCode: node.code,
      generalization: node.summary ? [{ text: node.summary, uid: `summary-${node.id}` }] : undefined,
      outerFrame: node.frame ? { groupId: node.frame.group_id, text: node.frame.text } : undefined,
      associativeLineTargets: lines.map((line) => line.target),
      associativeLineText: Object.fromEntries(lines.filter((line) => line.text).map((line) => [line.target, line.text])),
      associativeLinePoint: hasAnchors ? lines.map((line) => line.anchors || null) : undefined,
      associativeLineTargetControlOffsets: hasOffsets && lines.length ? lines.map((line) => line.offsets) : undefined,
      image: node.image?.data_url,
      imageSize: node.image ? { width: node.image.width, height: node.image.height } : undefined,
      icon: node.icon ? [node.icon] : undefined,
      ...hyperlinkData(node.hyperlink),
    },
    children: node.children.map((child) => toCanvas(child, full, badges)),
  }
}

export function fromCanvas({ data, children }) {
  const text = String(data.text ?? '').trim().slice(0, 320) || '未命名主题'
  return {
    id: data.uid, text, expanded: data.expand !== false, direction: data.dir || null,
    style: Object.fromEntries(styleKeys.filter((key) => data[key] != null).map((key) => [key, data[key]])),
    note: typeof data.mapNote === 'string' ? data.mapNote : '',
    sources: Array.isArray(data.mapSources) ? data.mapSources : [],
    labels: data.mapLabels || [],
    node_links: data.mapNodeLinks || [],
    formula: data.mapFormula || '',
    table: data.mapTable || null,
    code: data.mapCode || '',
    summary: String(data.generalization?.[0]?.text || '').slice(0, 160),
    frame: data.outerFrame ? { group_id: data.outerFrame.groupId, text: String(data.outerFrame.text || '').slice(0, 160) } : null,
    lines: (data.associativeLineTargets || []).map((target, index) => {
      const anchors = data.associativeLinePoint?.[index]
      const offsets = data.associativeLineTargetControlOffsets?.[index]
      return { target, text: String(data.associativeLineText?.[target] || '').slice(0, 160),
        anchors: anchors?.startPoint && anchors?.endPoint ? anchors : null, offsets: offsets || null }
    }),
    image: data.image && data.imageSize ? { data_url: data.image, width: data.imageSize.width, height: data.imageSize.height } : null,
    icon: data.icon?.[0] || null,
    hyperlink: data.hyperlink ? { url: data.hyperlink, label: data.mapHyperlinkLabel || '' } : null,
    children: (children || []).map(fromCanvas),
  }
}

export function createCanvas(element, document, options = {}) {
  const { readonly = false, full = false, dark = false, badges, ...overrides } = options
  return new MindMap({
    el: element, data: toCanvas(document.root, full, badges || (readonly ? labelBadges : editorBadges(document))), layout: document.layout,
    themeConfig: canvasTheme(document.palette, dark), readonly, fit: true,
    customCheckEnableShortcut: readonly ? () => false : undefined,
    customHyperlinkJump: (url) => {
      const target = new URL(url)
      if (target.protocol === 'https:' || target.protocol === 'http:') window.open(target.href, '_blank', 'noopener,noreferrer')
    },
    fitPadding: 20, hoverRectColor: '#9c86f5', textAutoWrapWidth: 210,
    createNewNodeBehavior: 'default', defaultInsertSecondLevelNodeText: '新主题',
    defaultInsertBelowSecondLevelNodeText: '新主题', enableFreeDrag: false,
    maxHistoryCount: 80, minExportImgCanvasScale: 2, exportPaddingX: 30, exportPaddingY: 30,
    maxTag: 24,
    ...overrides,
  })
}

export function flatNodes(root, depth = 0) {
  return [{ node: root, depth }, ...root.children.flatMap((child) => flatNodes(child, depth + 1))]
}

export function hyperlinkData(link) {
  return { hyperlink: link?.url || '', hyperlinkTitle: escapeSvgText(link?.label), mapHyperlinkLabel: link?.label || '' }
}
