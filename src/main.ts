import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import router from './router'
import App from './App.vue'

import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'
import './styles/global.css'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS,
  },
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)

app.mount('#app')
