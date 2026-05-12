import { defineStore } from 'pinia'
import { loginApi, meApi } from '../api/auth'
import { setClientCanteenSessionApi } from '../api/clientPortal'

const KEY_TOKEN = 'dz_token'
const KEY_ROLE = 'dz_role'
const KEY_USER = 'dz_user'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem(KEY_TOKEN) || '',
    role: localStorage.getItem(KEY_ROLE) || '',
    userInfo: JSON.parse(localStorage.getItem(KEY_USER) || 'null'),
  }),
  actions: {
    async login(form) {
      const res = await loginApi(form)
      this.token = res.token
      this.role = res.role
      localStorage.setItem(KEY_TOKEN, this.token)
      localStorage.setItem(KEY_ROLE, this.role)
      await this.fetchMe()
      return res
    },
    async fetchMe() {
      this.userInfo = await meApi()
      localStorage.setItem(KEY_USER, JSON.stringify(this.userInfo))
    },
    async applyCanteenSession(canteenId) {
      const res = await setClientCanteenSessionApi(canteenId)
      this.token = res.token
      localStorage.setItem(KEY_TOKEN, this.token)
      await this.fetchMe()
    },
    logout() {
      this.token = ''
      this.role = ''
      this.userInfo = null
      localStorage.removeItem(KEY_TOKEN)
      localStorage.removeItem(KEY_ROLE)
      localStorage.removeItem(KEY_USER)
    },
  },
})
