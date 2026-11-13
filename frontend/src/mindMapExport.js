import { canvasTheme, flatNodes, mapFontFamily } from './mindMapCanvas'

function groupPages(sources) {
  const groups = new Map()
  for (const { resource_id, start, end } of sources) {
    if (!groups.has(resource_id)) groups.set(resource_id, [])
    groups.get(resource_id).push([start, end])
  }
  return groups
}

function formatPages(ranges) {
  const merged = []
  for (const [start, end] of ranges.sort(([a], [b]) => a - b)) {
    const last = merged.at(-1)
    if (last && start <= last[1] + 1) last[1] = Math.max(last[1], end)
    else merged.push([start, end])
  }
  return `第 ${merged.map(([start, end]) => start === end ? start : `${start}–${end}`).join('、')} 页`
}

export function hasExportSources(map) {
  return map.sources.length > 0 || flatNodes(map.root).some(({ node }) => node.sources.length > 0)
}

function wrap(text, width, measure) {
  const lines = []
  let line = ''
  for (const character of text.replace(/\s+/gu, ' ')) {
    if (line && measure(line + character).width > width) {
      lines.push(line)
      line = ''
    }
    line += character
  }
  if (line) lines.push(line)
  return lines
}

function addSourceLegend(svg, entries) {
  const padding = 30
  const width = Math.max(svg.width(), 320)
  const top = svg.height()
  const ctx = document.createElement('canvas').getContext('2d')
  ctx.font = `13px ${mapFontFamily}`
  const lines = entries.flatMap((entry) => wrap(entry, width - padding * 2, ctx.measureText.bind(ctx)))
  svg.size(width, top + 50 + lines.length * 22)
  svg.line(padding, top, width - padding, top).stroke({ color: '#a7a4b2', width: 1 })
  svg.text('参考资料').font({ family: mapFontFamily, size: 14, weight: 700 }).fill('#302b3e').move(padding, top + 12)
  lines.forEach((line, index) => {
    svg.text(line).font({ family: mapFontFamily, size: 13 }).fill('#494255').move(padding, top + 36 + index * 22)
  })
  return svg
}

export function mapExportOptions(map, resources, includePages) {
  const options = { full: true, readonly: true, badges: () => [] }
  if (!includePages || !hasExportSources(map)) return options

  const whole = groupPages(map.sources)
  const ids = new Set(whole.keys())
  for (const { node } of flatNodes(map.root)) {
    for (const source of node.sources) ids.add(source.resource_id)
  }
  const numbers = new Map([...ids].map((id, index) => [id, index + 1]))
  const titles = new Map(resources.map(({ id, title }) => [id, title]))
  const prefix = (id) => ids.size > 1 ? `[${numbers.get(id)}] ` : ''
  const legend = [...ids].map((id) => {
    const title = titles.get(id) || '资料已不可用'
    const pages = whole.has(id) ? `（整图选用${formatPages(whole.get(id))}）` : ''
    return `${prefix(id)}${title}${pages}`
  })
  const themeConfig = canvasTheme(map.palette)
  for (const level of ['root', 'second', 'node']) themeConfig[level].tagPlacement = 'bottom'
  return {
    ...options, themeConfig, maxTag: 12,
    badges: (node) => [...groupPages(node.sources)]
      .sort(([a], [b]) => numbers.get(a) - numbers.get(b))
      .map(([id, pages]) => ({
        text: `${prefix(id)}${formatPages(pages)}`,
        style: { fill: '#5b5369', fontSize: 11, height: 17, paddingX: 5 },
      })),
    handleBeingExportSvg: (svg) => addSourceLegend(svg, legend),
  }
}
