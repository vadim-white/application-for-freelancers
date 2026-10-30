<template>
  <div class="login-container">
    <div class="login-content">
      <div class="login-header">
        <h1 class="login-title">
          <span class="gradient-text">Freelance Service</span>
        </h1>
        <p class="login-subtitle">Система управления проектами и временем</p>
      </div>

      <n-card style="max-width: 420px">
        <template #header>
          <div style="text-align: center; width: 100%">
            <h2 style="margin: 0; color: var(--color-text-primary)">Вход в систему</h2>
          </div>
        </template>

        <n-form ref="formRef" :model="form">
          <n-form-item label="Email" path="email">
            <n-input
              v-model:value="form.email"
              :input-props="{ type: 'email', autocomplete: 'email' }"
              placeholder="your@email.com"
              clearable
              @keyup.enter="onSubmit"
            />
          </n-form-item>

          <n-form-item label="Пароль" path="password">
            <n-input
              v-model:value="form.password"
              type="password"
              placeholder="••••••••"
              show-password-on="click"
              @keyup.enter="onSubmit"
            />
          </n-form-item>

          <div style="margin-top: 24px; text-align: center">
            <n-button
              type="primary"
              :loading="loading"
              style="width: 100%; padding: 10px"
              size="large"
              @click="onSubmit"
            >
              Войти
            </n-button>
          </div>
        </n-form>

        <template #footer>
          <div style="text-align: center; color: var(--color-text-secondary); font-size: 14px">
            Еще не зарегистрированы?
            <router-link
              to="/register"
              style="
                color: var(--color-primary);
                text-decoration: none;
                font-weight: 600;
                cursor: pointer;
              "
            >
              Зарегистрироваться
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
import { useAuthStore } from '../stores/auth'
import { NButton, NCard, NForm, NFormItem, NInput, useMessage } from 'naive-ui'
import { authErrorText } from '../services/errors'

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()

const formRef = ref()
const form = ref({ email: '', password: '' })
const loading = ref(false)

async function onSubmit() {
  if (!form.value.email || !form.value.password) {
    message.error('Введите email и пароль')
    return
  }
  loading.value = true
  try {
    await auth.login(form.value.email, form.value.password)
    message.success('Успешный вход')
    router.push('/dashboard')
  } catch (err) {
    message.error(authErrorText(err, 'Ошибка входа'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #10b981 0%, #f59e0b 100%);
  padding: 20px;
}

.login-content {
  width: 100%;
  max-width: 420px;
  animation: slideInUp 0.5s ease-out;
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
  color: white;
}

.login-title {
  font-size: 40px;
  margin-bottom: 8px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.login-subtitle {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.8);
  margin: 0;
  font-weight: 500;
}

@media (max-width: 640px) {
  .login-container {
    padding: 16px;
  }

  .login-title {
    font-size: 32px;
  }

  .login-content {
    max-width: 100%;
  }
}
</style>
