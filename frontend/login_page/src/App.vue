<template>
  <n-config-provider :theme-overrides="overrides">
    <n-message-provider>
      <router-view />
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { palettes, themeOverrides } from './styles/tokens'

// Светлая тема; тёмную и переключатель добавляет 3.2.5
const overrides = themeOverrides(palettes.light)
</script>
