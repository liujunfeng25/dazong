export function createReconnectingWS(url, { onMessage, reconnectMs = 3000 } = {}) {
  let ws = null
  let closedByUser = false
  let reconnectTimer = null

  const connect = () => {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws = new WebSocket(url)
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data)
        onMessage && onMessage(data)
      } catch {
        // ignore parse errors
      }
    }
    ws.onclose = () => {
      if (!closedByUser) reconnectTimer = setTimeout(connect, reconnectMs)
    }
    ws.onerror = () => {
      if (ws && ws.readyState < 2) ws.close()
    }
  }

  connect()

  return {
    send(payload) {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(typeof payload === 'string' ? payload : JSON.stringify(payload))
      }
    },
    close() {
      closedByUser = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
    },
  }
}
