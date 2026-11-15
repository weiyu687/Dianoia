import { ref, shallowRef } from 'vue'
import { height } from './presentation'

function styleFor(effect, progress, item) {
  if (effect === 'fade_in') return { opacity: progress }
  if (effect === 'fade_out') return { opacity: 1 - progress }
  if (effect === 'fly_in') return { dy: (height - item.y) * (1 - progress) }
  return { scale: 1 + .12 * Math.sin(Math.PI * progress) }
}

export function usePresentationPlayback() {
  const states = shallowRef({})
  const running = ref(false)
  const cursor = ref(0)
  let animations = []
  let elements = new Map()
  let frame

  function stop() {
    cancelAnimationFrame(frame)
    frame = undefined
    running.value = false
  }

  function run(allowClick) {
    const effect = animations[cursor.value]
    if (!effect || running.value || (!allowClick && effect.trigger === 'click')) return false
    running.value = true
    const item = elements.get(effect.target_id)
    const previous = states.value[item.id] || {}
    const style = (progress) => ({ ...styleFor(effect.effect, progress, item),
      ...(effect.effect === 'emphasis' ? { opacity: previous.opacity ?? 1 } : {}) })
    const duration = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : effect.duration_ms
    const start = performance.now()

    const draw = (now) => {
      const progress = duration ? Math.min(1, Math.max(0, (now - start) / duration)) : 1
      states.value = { ...states.value, [item.id]: style(progress) }
      if (progress < 1) {
        frame = requestAnimationFrame(draw)
        return
      }
      cursor.value++
      frame = undefined
      running.value = false
      run(false)
    }

    states.value = { ...states.value, [item.id]: style(0) }
    frame = requestAnimationFrame(draw)
    return true
  }

  function enter(slide) {
    stop()
    animations = slide.animations || []
    elements = new Map(slide.elements.map((item) => [item.id, item]))
    const initial = {}
    for (const entry of animations) {
      if (entry.target_id in initial) continue
      initial[entry.target_id] = ['fade_in', 'fly_in'].includes(entry.effect) ? { opacity: 0 } : {}
    }
    states.value = initial
    cursor.value = 0
    run(false)
  }

  return { states, running, cursor, enter, stop, advance: () => running.value || run(true) }
}
