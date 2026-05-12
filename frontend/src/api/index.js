import axios from 'axios'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import router from '../router'

const http = axios.create({
  baseURL: '/api',
  timeout: 10000,
})

http.interceptors.request.use((config) => {
  const store = useUserStore()
  if (store.token) {
    config.headers.Authorization = `Bearer ${store.token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error?.response?.status
    const detail = error?.response?.data?.detail
    const message =
      (Array.isArray(detail) ? detail.map((i) => i?.msg).filter(Boolean).join('；') : detail) ||
      error?.message ||
      '请求失败，请稍后重试'

    if (error?.response?.status === 401) {
      const store = useUserStore()
      store.logout()
      router.replace('/login')
      ElMessage.error('登录状态失效，请重新登录')
      return Promise.reject(error)
    }
    if (status && status >= 400) ElMessage.error(message)
    return Promise.reject(error)
  },
)

export default http
