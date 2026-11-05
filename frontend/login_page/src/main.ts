import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import { RELOAD_FLAG, chunkError } from './services/chunkError'

import '@fontsource-variable/onest/wght.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import './styles/global.css'

const app = createApp(App)

// Pinia раньше роутера: redirect-функция роута «/» читает стор при установке роутера
app.use(createPinia())
app.use(router)

// Страницы грузятся отдельными чанками. Вкладка, открытая до выкатки, просит чанк старой сборки,
// а в новом образе его нет (nginx отдаёт 404) — переход молча ломается. Одна перезагрузка на адрес
// перехода берёт свежий index.html; флаг в sessionStorage не даёт зациклиться, если чанка нет и после неё:
// тогда App.vue показывает ошибку с «Повторить» (chunkError)
let chunkFailed = false
window.addEventListener('vite:preloadError', () => {
  chunkFailed = true
})
router.onError((_error, to) => {
  if (!chunkFailed) return
  chunkFailed = false
  if (sessionStorage.getItem(RELOAD_FLAG)) {
    chunkError.value = to.fullPath
    return
  }
  sessionStorage.setItem(RELOAD_FLAG, '1')
  window.location.assign(to.fullPath)
})
router.afterEach((_to, _from, failure) => {
  if (!failure) {
    sessionStorage.removeItem(RELOAD_FLAG)
    chunkError.value = null
  }
})

app.mount('#app')
