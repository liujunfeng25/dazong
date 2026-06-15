import http from './index'

const tokenHeader = () => {
  const token = localStorage.getItem('dz_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// AI 对话可能涉及多轮工具调用与 LLM 推理，不设超时
export const postChat = (payload) => http.post('/chat', payload, { timeout: 0 })

export const exportChatReport = (payload) =>
  http.post('/chat/report/export', payload, { responseType: 'blob', timeout: 0 })

export const searchChatDocs = (q, limit = 5) =>
  http.get('/chat/docs/search', { params: { q, limit } })

export const streamChat = async (payload, handlers = {}) => {
  const response = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...tokenHeader(),
    },
    body: JSON.stringify(payload),
  })
  if (!response.ok || !response.body) {
    throw new Error(`AI 对话流请求失败：${response.status}`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const eventLine = part.split('\n').find((line) => line.startsWith('event:'))
      const dataLine = part.split('\n').find((line) => line.startsWith('data:'))
      const event = eventLine?.replace('event:', '').trim() || 'message'
      const data = dataLine ? JSON.parse(dataLine.replace('data:', '').trim()) : {}
      handlers[event]?.(data)
    }
  }
}
