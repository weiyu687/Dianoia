export const width = 960
export const height = 540
export const labels = { text: '文本框', shape: '形状', image: '图片', table: '表格', chart: '图表', formula: '公式' }
export const layouts = { blank: '空白', cover: '封面', body: '标题与正文', two: '双栏', steps: '步骤', table: '表格' }
export const shapes = {
  rect: '矩形', round: '圆角矩形', ellipse: '椭圆', triangle: '三角形', diamond: '菱形', hexagon: '六边形',
  pentagon: '五边形', parallelogram: '平行四边形', trapezoid: '梯形', star: '五角星', callout: '标注框',
  arrow: '右箭头', arrowLeft: '左箭头', arrowUp: '上箭头', arrowDown: '下箭头', chevron: '燕尾箭头',
  line: '水平线', connector: '直线', connectorArrow: '箭头线',
}
export const shapePolygons = {
  triangle: [.5,0,1,1,0,1],
  diamond: [.5,0,1,.5,.5,1,0,.5],
  hexagon: [.24,0,.76,0,1,.5,.76,1,.24,1,0,.5],
  parallelogram: [.2,0,1,0,.8,1,0,1],
  trapezoid: [.22,0,.78,0,1,1,0,1],
  chevron: [0,0,.72,0,1,.5,.72,1,0,1,.3,.5],
  pentagon: [.5,0,1,.38,.81,1,.19,1,0,.38],
  arrow: [0,.25,.58,.25,.58,0,1,.5,.58,1,.58,.75,0,.75],
  arrowLeft: [1,.25,.42,.25,.42,0,0,.5,.42,1,.42,.75,1,.75],
  arrowUp: [.25,1,.25,.42,0,.42,.5,0,1,.42,.75,.42,.75,1],
  arrowDown: [.25,0,.25,.58,0,.58,.5,1,1,.58,.75,.58,.75,0],
  star: [.5,0,.62,.35,1,.38,.71,.61,.8,1,.5,.77,.2,1,.29,.61,0,.38,.38,.35],
  callout: [0,0,1,0,1,.76,.43,.76,.22,1,.22,.76,0,.76],
}
export const shapeGroups = {
  矩形: ['rect', 'round'],
  常用形状: ['ellipse', 'triangle', 'diamond', 'hexagon', 'pentagon', 'parallelogram', 'trapezoid', 'star', 'callout'],
  箭头: ['arrow', 'arrowLeft', 'arrowUp', 'arrowDown', 'chevron'],
}
export const chartTypes = { column: '柱状图', bar: '条形图', line: '折线图', area: '面积图',
  scatter: '散点图', pie: '饼图', donut: '环形图', radar: '雷达图' }
export const transitions = { none: '无', fade: '淡入', push: '推入' }
export const fonts = ['Microsoft YaHei', 'SimSun', 'SimHei', 'Arial', 'Consolas']
export const slideFontNames = { 'Microsoft YaHei': '微软雅黑', SimSun: '宋体', SimHei: '黑体' }
export const uid = () => crypto.randomUUID()
export const clone = (data) => JSON.parse(JSON.stringify(data))
export const slideTitle = (slide) => slide.elements.find((item) => item.role === 'title')?.text ||
  slide.elements.find((item) => item.kind === 'text' && item.text.trim())?.text.split('\n')[0] || '空白页'

export function readableInk(background) {
  const [r, g, b] = [1, 3, 5].map((index) => parseInt(background.slice(index, index + 2), 16) / 255)
  const linear = (channel) => channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4
  const luminance = .2126 * linear(r) + .7152 * linear(g) + .0722 * linear(b)
  return luminance < .25 ? '#ffffff' : '#172b42'
}

export function newElement(kind, fields = {}) {
  const defaults = {
    text: { text: '双击编辑文字', size: 25 },
    shape: { width: 170, height: 100, shape: 'rect' },
    table: { width: 580, height: 200, rows: [['列一', '列二', '列三'], ['', '', ''], ['', '', '']], size: 18 },
    chart: { width: 500, height: 300, labels: ['一', '二', '三'], values: [20, 35, 28], chart: 'column' },
  }
  return { id: uid(), kind, x: 80, y: 88, width: 280, height: 76, rotation: 0, locked: false,
    fill: '#436790', color: '#172b42', align: 'left', font: 'Microsoft YaHei', ...defaults[kind], ...fields }
}

export function newSlide(layout = 'blank') {
  const elements = []
  const dark = layout === 'cover'
  if (layout !== 'blank') {
    elements.push(newElement('text', { role: 'title', text: dark ? '课程主题' : '本页标题',
      x: 65, y: dark ? 164 : 55, width: 830, height: 90, size: dark ? 52 : 38, bold: true,
      color: dark ? '#ffffff' : '#172b42' }))
    if (layout === 'table') {
      elements.push(newElement('table', { x: 65, y: 168, width: 830, height: 290 }))
    } else if (layout === 'two') {
      for (const x of [65, 492]) elements.push(newElement('text', { role: 'body', text: '填写教学内容',
        x, y: 155, width: 400, height: 300, size: 26 }))
    } else {
      elements.push(newElement('text', { role: 'body', text: dark ? '主讲教师 · 教学班' :
        layout === 'steps' ? '01  准备\n\n02  演示\n\n03  练习' : '填写教学内容',
        x: 65, y: dark ? 312 : 155, width: 830, height: dark ? 72 : 300, size: 25,
        color: dark ? '#dce8f3' : '#172b42' }))
    }
  }
  return { id: uid(), background: dark ? '#17375d' : '#ffffff', layout, notes: '', citations: [], elements }
}
