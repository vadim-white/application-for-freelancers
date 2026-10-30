<template>
  <div class="register-container">
    <div class="register-content">
      <div class="register-header">
        <h1 class="register-title">Создать аккаунт</h1>
        <p class="register-subtitle">Присоединитесь к системе управления проектами</p>
      </div>

      <n-card>
        <template #header>
          <div style="text-align: center; width: 100%">
            <h2 style="margin: 0; color: var(--color-text)">Регистрация</h2>
          </div>
        </template>

        <n-form :model="form">
          <n-form-item label="Email" path="email">
            <n-input
              v-model:value="form.email"
              :input-props="{ type: 'email', autocomplete: 'email' }"
              placeholder="your@email.com"
              clearable
              @keyup.enter="onRegister"
            />
          </n-form-item>

          <n-form-item label="Полное имя" path="full_name">
            <n-input
              v-model:value="form.full_name"
              placeholder="Ваше имя"
              clearable
              @keyup.enter="onRegister"
            />
          </n-form-item>

          <n-form-item label="Пароль" path="password">
            <n-input
              v-model:value="form.password"
              type="password"
              placeholder="••••••••"
              show-password-on="click"
              @keyup.enter="onRegister"
            />
          </n-form-item>

          <div style="margin-top: 24px; text-align: center">
            <n-button
              type="primary"
              :loading="loading"
              style="width: 100%; padding: 10px"
              size="large"
              @click="onRegister"
            >
              Зарегистрироваться
            </n-button>
          </div>
        </n-form>

        <template #footer>
          <div style="text-align: center; color: var(--color-text-secondary); font-size: 14px">
            Уже есть аккаунт?
            <router-link
              to="/login"
              style="
                color: var(--color-accent);
                text-decoration: none;
                font-weight: 600;
                cursor: pointer;
              "
            >
              Войти
            </router-link>
          </div>
        </template>
      </n-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NCard, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import { authErrorText } from '../services/errors'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()
const form = ref({ email: '', password: '', full_name: '' })
const loading = ref(false)

async function onRegister() {
  if (!form.value.email || !form.value.password || !form.value.full_name) {
    message.error('Заполните все поля')
    return
  }
  loading.value = true
  try {
    await auth.register(form.value)
    message.success('Зарегистрировано — выполните вход')
    router.push('/login')
  } catch (e) {
    message.error(authErrorText(e, 'Ошибка регистрации'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.register-content {
  width: 100%;
  max-width: 420px;
  animation: slideInUp 0.5s ease-out;
}

.register-header {
  text-align: center;
  margin-bottom: 40px;
  color: var(--color-text);
}

.register-title {
  font-size: 36px;
  margin-bottom: 8px;
  font-weight: var(--weight-heading);
  letter-spacing: -0.5px;
}

.register-subtitle {
  font-size: 16px;
  color: var(--color-text-secondary);
  margin: 0;
  font-weight: var(--weight-text);
}

@media (max-width: 640px) {
  .register-container {
    padding: 16px;
  }

  .register-title {
    font-size: 28px;
  }

  .register-content {
    max-width: 100%;
  }
}
</style>
