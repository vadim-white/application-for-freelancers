<template>
  <div class="app-layout">
    <header class="app-header" data-testid="app-header">
      <button
        ref="menuButton"
        type="button"
        class="header-button menu-button"
        aria-label="Меню разделов"
        aria-controls="app-nav"
        :aria-expanded="menuOpen"
        @click="menuOpen = !menuOpen"
      >
        <app-icon :icon="menuOpen ? X : Menu" :size="20" />
      </button>

      <router-link to="/dashboard" class="brand">
        <brand-mark />
        <span class="brand-name">Freelance Service</span>
      </router-link>

      <nav id="app-nav" class="app-nav" :class="{ open: menuOpen }" @click="onNavClick">
        <router-link to="/dashboard" class="nav-link">
          <app-icon :icon="ListChecks" />
          Проекты
        </router-link>
        <template v-if="isAdmin">
          <router-link to="/statistics" class="nav-link">
            <app-icon :icon="ChartColumn" />
            Статистика
          </router-link>
          <router-link to="/users" class="nav-link">
            <app-icon :icon="Users" />
            Пользователи
          </router-link>
        </template>
      </nav>

      <span class="spacer" />

      <!-- Переключатель темы (3.2.5) -->

      <div v-if="auth.user" class="user">
        <span class="avatar">{{ initial }}</span>
        <span class="user-text">
          <span class="user-name">{{ auth.user.full_name || auth.user.email }}</span>
          <span class="user-role">
            <app-icon :icon="isAdmin ? Crown : User" :size="12" />
            {{ isAdmin ? 'Администратор' : 'Пользователь' }}
          </span>
        </span>
      </div>
      <span class="separator" />
      <router-link to="/profile" class="header-button action" title="Профиль">
        <app-icon :icon="User" />
        <span class="action-label">Профиль</span>
      </router-link>
      <button type="button" class="header-button action" title="Выйти" @click="auth.logout()">
        <app-icon :icon="LogOut" />
        <span class="action-label">Выйти</span>
      </button>
    </header>

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ChartColumn, Crown, ListChecks, LogOut, Menu, User, Users, X } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import BrandMark from '../components/BrandMark.vue'
import { useAuthStore } from '../stores/auth'

// Раскладка страниц после входа: общая шапка и страница под ней. На узком экране разделы уходят
// в меню под кнопкой; меню закрывается по выбору раздела и по Esc
const auth = useAuthStore()
const route = useRoute()

const isAdmin = computed(() => auth.user?.role === 'admin')
const initial = computed(() =>
  (auth.user?.full_name || auth.user?.email || '').charAt(0).toUpperCase()
)

const menuOpen = ref(false)
const menuButton = ref<HTMLButtonElement | null>(null)

watch(
  () => route.fullPath,
  () => (menuOpen.value = false)
)

// выбор открытого раздела адрес не меняет — закрываем по щелчку по ссылке
function onNavClick(event: MouseEvent) {
  if ((event.target as HTMLElement).closest('a')) menuOpen.value = false
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !menuOpen.value) return
  menuOpen.value = false
  menuButton.value?.focus()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.app-layout {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.app-header {
  position: relative;
  height: 56px;
  display: flex;
  align-items: center;
  gap: var(--space-6);
  padding: 0 var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-line);
}

.app-main {
  flex: 1;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text);
  font-weight: var(--weight-heading);
  font-size: 16px;
  text-decoration: none;
  white-space: nowrap;
}

.app-nav {
  display: flex;
  gap: var(--space-1);
}

.nav-link,
.header-button {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 36px;
  padding: 0 var(--space-3);
  border: 0;
  border-radius: var(--radius-md);
  background: none;
  color: var(--color-text-secondary);
  font-weight: var(--weight-strong);
  font-size: 14px;
  text-decoration: none;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--transition),
    color var(--transition);
}

.nav-link:hover,
.header-button:hover {
  background: var(--color-surface-hover);
  color: var(--color-text);
}

.nav-link.router-link-active {
  background: var(--color-accent-soft);
  color: var(--color-text);
}

.nav-link:focus-visible,
.header-button:focus-visible,
.brand:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.menu-button {
  display: none;
  width: 36px;
  padding: 0;
  justify-content: center;
  color: var(--color-text);
}

.spacer {
  flex: 1;
}

.user {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--color-accent-soft);
  color: var(--color-text);
  font-weight: var(--weight-strong);
}

.user-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.2;
}

.user-name {
  font-weight: var(--weight-strong);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.user-role {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: 12px;
  color: var(--color-text-secondary);
}

.separator {
  width: 1px;
  height: 24px;
  background: var(--color-line);
  margin: 0 calc(-1 * var(--space-3));
}

.action {
  padding: 0 10px;
}

/* Ширина, где имя и роль уже не помещаются рядом с разделами: остаётся аватар */
@media (max-width: 1100px) {
  .user-text {
    display: none;
  }
}

/* Узкий экран: одна строка — кнопка меню, знак, аватар, «Профиль» и «Выйти» иконками;
   разделы — в выпадающем меню под шапкой */
@media (max-width: 960px) {
  .app-header {
    gap: var(--space-2);
    padding: 0 var(--space-4);
  }

  .menu-button {
    display: inline-flex;
  }

  .brand-name {
    display: none;
  }

  .app-nav {
    display: none;
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 10;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2) var(--space-4) var(--space-3);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-line);
    box-shadow: var(--shadow-overlay);
  }

  .app-nav.open {
    display: flex;
  }

  .nav-link {
    height: 44px;
    font-size: 15px;
  }

  .separator {
    display: none;
  }

  .action {
    width: 36px;
    padding: 0;
    justify-content: center;
  }

  /* подпись остаётся для скринридера, зрячему — иконка и подсказка title */
  .action-label {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
}
</style>
