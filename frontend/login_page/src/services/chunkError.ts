import { ref } from 'vue'

// Отметка «страницу уже перезагружали из-за чанка» (J6, main.ts) и адрес, который не открылся:
// если чанка нет и после перезагрузки, App.vue показывает ошибку с «Повторить» вместо пустой страницы
export const RELOAD_FLAG = 'chunk-reload'
export const chunkError = ref<string | null>(null)
