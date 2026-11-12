export async function api(path, options = {}) {
  const headers = { 'X-Dianoia-Client': 'web', ...options.headers }
  let body = options.body
  if (body && !(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(body)
  }
  const response = await fetch(`/api${path}`, { ...options, body, headers, credentials: 'same-origin' })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const issue = Array.isArray(payload.detail)
      ? payload.detail.find((item) => typeof item?.msg === 'string')
      : null
    const message = typeof payload.detail === 'string' ? payload.detail
      : issue?.msg || '请求失败，请检查输入后重试'
    throw Object.assign(new Error(message), { status: response.status })
  }
  if (response.status === 204) return null
  return options.binary ? response : response.json()
}

export async function download(path, fallback) {
  const response = await api(path, { binary: true })
  const disposition = response.headers.get('content-disposition') || ''
  const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = encodedName ? decodeURIComponent(encodedName) : fallback
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const formatDate = (value) => new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(value + (value.endsWith('Z') ? '' : 'Z')))

export const formatSize = (bytes) => bytes >= 1024 * 1024
  ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  : `${Math.max(1, Math.round(bytes / 1024))} KB`
