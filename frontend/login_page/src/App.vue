<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="overrides">
    <n-message-provider>
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import {
  NConfigProvider,
  NMessageProvider,
  alertDark,
  buttonDark,
  cardDark,
  commonDark,
  datePickerDark,
  dialogDark,
  drawerDark,
  formDark,
  inputDark,
  messageDark,
  modalDark,
  paginationDark,
  selectDark,
  spaceDark,
  spinDark,
  switchDark,
  tagDark,
  type GlobalTheme
} from 'naive-ui'
import { computed } from 'vue'
import { useThemeStore } from './stores/theme'
import { palettes, themeOverrides } from './styles/tokens'

// Тёмные темы только тех компонентов Naive UI, что импортируются в src/ (вложенные части —
// выпадающий список селекта, календарь — приходят в их peers): darkTheme целиком тянет все
// компоненты, +38,7 kB к стартовому чанку. Новый компонент Naive UI — добавить сюда его тёмную тему
const darkTheme: GlobalTheme = {
  name: 'dark',
  common: commonDark,
  Alert: alertDark,
  Button: buttonDark,
  Card: cardDark,
  DatePicker: datePickerDark,
  Dialog: dialogDark,
  Drawer: drawerDark,
  Form: formDark,
  Input: inputDark,
  Message: messageDark,
  Modal: modalDark,
  Pagination: paginationDark,
  Select: selectDark,
  Space: spaceDark,
  Spin: spinDark,
  Switch: switchDark,
  Tag: tagDark
}

// Тема Naive UI идёт за стором темы: тёмные темы и overrides тёмной палитры или светлые
const theme = useThemeStore()
const lightOverrides = themeOverrides(palettes.light)
const darkOverrides = themeOverrides(palettes.dark)
const naiveTheme = computed(() => (theme.resolved === 'dark' ? darkTheme : null))
const overrides = computed(() => (theme.resolved === 'dark' ? darkOverrides : lightOverrides))
</script>
