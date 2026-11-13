import MindMap from 'simple-mind-map'
import Drag from 'simple-mind-map/src/plugins/Drag.js'
import Export from 'simple-mind-map/src/plugins/Export.js'
import KeyboardNavigation from 'simple-mind-map/src/plugins/KeyboardNavigation.js'

MindMap.usePlugin(Drag).usePlugin(Export).usePlugin(KeyboardNavigation)
MindMap.extendNodeDataNoStylePropList(['mapNote', 'mapSources'])

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

const fontFamily = 'Microsoft YaHei UI, PingFang SC, Noto Sans CJK SC, sans-serif'
const styleKeys = ['fillColor', 'color', 'borderColor', 'lineColor', 'fontSize', 'fontWeight', 'shape']

export function canvasTheme(palette, dark = false) {
  const { root, fill, border, paper } = palettes[palette]
  const node = { fontFamily, shape: 'roundedRectangle', borderWidth: 1 }
  return {
    backgroundColor: dark ? '#1d1d26' : paper,
    lineColor: dark ? border : root, lineWidth: 1.5, lineRadius: 9, paddingY: 8, paddingX: 13,
    root: { ...node, fillColor: root, color: '#ffffff', borderColor: root, fontSize: 21 },
    second: { ...node, fillColor: fill, color: '#231d34', borderColor: border, fontSize: 16, fontWeight: 'bold', marginX: 56, marginY: 20 },
    node: { ...node, fillColor: '#ffffff', color: '#262331', borderColor: border, fontSize: 14, marginX: 34, marginY: 12 },
  }
}

export function toCanvas(node, full = false) {
  return {
    data: {
      uid: node.id, text: node.text, expand: full || node.expanded, dir: node.direction || undefined,
      ...node.style, mapNote: node.note, mapSources: node.sources,
      tag: nodeBadges(node.note, node.sources),
    },
    children: node.children.map((child) => toCanvas(child, full)),
  }
}

export function nodeBadges(note, sources) {
  return [
    ...(note ? ['备注'] : []),
    ...(sources?.length ? [`资料 ${sources.length}`] : []),
  ]
}

export function fromCanvas({ data, children }) {
  const text = String(data.text ?? '').trim().slice(0, 320) || '未命名主题'
  return {
    id: data.uid, text, expanded: data.expand !== false, direction: data.dir || null,
    style: Object.fromEntries(styleKeys.filter((key) => data[key] != null).map((key) => [key, data[key]])),
    note: typeof data.mapNote === 'string' ? data.mapNote : '',
    sources: Array.isArray(data.mapSources) ? data.mapSources : [],
    children: (children || []).map(fromCanvas),
  }
}

export function createCanvas(element, document, options = {}) {
  const { readonly = false, full = false, dark = false, ...overrides } = options
  return new MindMap({
    el: element, data: toCanvas(document.root, full), layout: document.layout,
    themeConfig: canvasTheme(document.palette, dark), readonly, fit: true,
    customCheckEnableShortcut: readonly ? () => false : undefined,
    fitPadding: 20, hoverRectColor: '#9c86f5', textAutoWrapWidth: 210,
    createNewNodeBehavior: 'default', defaultInsertSecondLevelNodeText: '新主题',
    defaultInsertBelowSecondLevelNodeText: '新主题', enableFreeDrag: false,
    maxHistoryCount: 80, minExportImgCanvasScale: 2, exportPaddingX: 30, exportPaddingY: 30,
    ...overrides,
  })
}

export function flatNodes(root, depth = 0) {
  return [{ node: root, depth }, ...root.children.flatMap((child) => flatNodes(child, depth + 1))]
}
