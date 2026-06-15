import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import 'element-plus/dist/index.css'
import '@unocss/reset/tailwind.css'
import 'uno.css'
import './styles/theme.css'
import './styles/mobile-theme.css'
import './styles/portal-skin.css'
import App from './App.vue'
import router from './router'

dayjs.locale('zh-cn')

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
