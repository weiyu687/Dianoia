import { computed, ref } from 'vue'
import { animationEffects, height } from './presentation'

const resting = { opacity: 1, dy: 0, scale: 1 }
const hidden = { ...resting, opacity: 0 }
const isEntrance = (effect) => effect === 'fade_in' || effect === 'fly_in'
const ease = (progress) => progress * progress * (3 - 2 * progress)

function effectFrame(effect, progress, item, visible, reducedMotion) {
  const amount = ease(progress)
  if (effect === 'fade_out') return { ...resting, opacity: visible ? 1 - amount : 0 }
  if (effect === 'fade_in' || (effect === 'fly_in' && reducedMotion)) return { ...resting, opacity: amount }
  if (effect === 'fly_in') {
    const radians = item.rotation * Math.PI / 180
    const top = item.y + Math.min(0, item.width * Math.sin(radians)) + Math.min(0, item.height * Math.cos(radians))
    const distance = Math.max(0, height - top + 4)
    return { ...resting, dy: distance * (1 - progress) ** 3 }
  }
  const pulse = ease(1 - Math.abs(2 * progress - 1))
  if (!visible) return hidden
  return reducedMotion ? { ...resting, opacity: 1 - .25 * pulse } : { ...resting, scale: 1 + .12 * pulse }
}

export function usePresentationPlayback() {
  const running = ref(false)
  const cursor = ref(0)
  const length = ref(0)
  const pending = computed(() => cursor.value < length.value)
  let animations = []
  const targets = new Map()
  let render
  let preview = false
  let reducedMotion = false
  let frame
  let hold

  function stop() {
    cancelAnimationFrame(frame)
    clearTimeout(hold)
    frame = hold = undefined
    render?.reset()
    render = undefined
    animations = []
    targets.clear()
    running.value = false
    cursor.value = length.value = 0
  }

  function run(allowClick) {
    const entry = animations[cursor.value]
    if (!entry || (!allowClick && entry.trigger === 'click')) return false
    const target = targets.get(entry.target_id)
    const { item, visible } = target
    const duration = entry.duration_ms
    let start
    running.value = true

    const paint = (progress) => render.set(item.id, effectFrame(entry.effect, progress, item, visible, reducedMotion))
    const finish = () => {
      if (isEntrance(entry.effect)) target.visible = true
      if (entry.effect === 'fade_out') target.visible = false
      cursor.value++
      if (preview && !pending.value) stop()
      else if (!run(preview)) running.value = false
    }
    const draw = (now) => {
      start ??= now
      const progress = Math.min(1, (now - start) / duration)
      paint(progress)
      if (progress < 1) frame = requestAnimationFrame(draw)
      else {
        frame = undefined
        // Hold the final preview frame briefly so a fade-out can be seen before the object is restored.
        if (preview) hold = setTimeout(finish, 240)
        else finish()
      }
    }
    paint(0)
    frame = requestAnimationFrame(draw)
    return true
  }

  function enter(slide, canvas, { entries = slide.animations, isPreview = false } = {}) {
    stop()
    if (!canvas) return
    const items = new Map(slide.elements.map((item) => [item.id, item]))
    animations = (entries || []).filter((entry) => Object.hasOwn(animationEffects, entry.effect) && items.has(entry.target_id))
    preview = isPreview
    reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    length.value = animations.length
    if (!length.value) return
    for (const entry of animations) {
      if (targets.has(entry.target_id)) continue
      targets.set(entry.target_id, { item: items.get(entry.target_id), visible: !isEntrance(entry.effect) })
    }
    render = canvas.bindMotion([...targets.values()].map(({ item }) => item))
    for (const [id, target] of targets) {
      if (!target.visible) render.set(id, hidden)
    }
    run(preview)
  }

  return { running, pending, enter, stop, advance: () => running.value || (pending.value && run(true)) }
}
