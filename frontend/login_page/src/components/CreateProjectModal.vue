<template>
  <n-modal
    v-model:show="innerShow"
    :closable="true"
    preset="dialog"
    style="min-width:420px"
  >
    <template #header>
      <div style="font-weight: 600; color: var(--color-text-primary)">📋 Создать новый проект</div>
    </template>

    <template #default>
      <div style="padding: 16px 0">
        <n-form label-placement="top" :model="form">
          <n-form-item label="Название проекта" path="name">
            <n-input
              v-model:value="form.name"
              placeholder="Введите название..."
              autofocus
              clearable
              maxlength="100"
            />
          </n-form-item>

          <n-form-item label="Описание" path="description">
            <n-input
              type="textarea"
              v-model:value="form.description"
              placeholder="Краткое описание проекта (опционально)"
              rows="4"
              maxlength="500"
              show-count
            />
          </n-form-item>
        </n-form>
      </div>
    </template>

    <template #action>
      <n-space justify="end">
        <n-button @click="onCancel">Отмена</n-button>
        <n-button
          type="primary"
          :loading="saving"
          @click="onSave"
        >
          ✓ Создать
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { createProject as createTaskProject } from '../services/tasks'
import { createProject as createTimeProject } from '../services/time'
import { useMessage } from 'naive-ui'

/* props / emits */
const props = defineProps({
  show: { type: Boolean, default: false }
})
const emit = defineEmits(['update:show', 'created'])

/* видимость модалки — синхронизируем с родителем */
const innerShow = ref(props.show)
watch(() => props.show, (v) => (innerShow.value = v))
watch(innerShow, (v) => emit('update:show', v))

/* форма и состояния */
const form = reactive({ name: '', description: '' })
const saving = ref(false)
const message = useMessage()

function onCancel() {
  form.name = ''
  form.description = ''
  innerShow.value = false
}

/* создаём проект сразу в двух сервисах */
async function onSave() {
  if (!form.name || !form.name.trim()) {
    message.error('Введите название проекта')
    return
  }

  saving.value = true
  try {
    // 1️⃣ создаём проект в task-service
    const createdTaskProject = await createTaskProject({
      name: form.name.trim(),
      description: form.description?.trim() || ''
    })

    // 2️⃣ создаём проект в time-service
    try {
      await createTimeProject({
        name: createdTaskProject.name,
        description: createdTaskProject.description || '',
        external_id: createdTaskProject.id  // синхронизация через external_id
      })
    } catch (err) {
      console.warn('Не удалось создать проект в time-service, таймеры могут не работать', err)
    }

    message.success('Проект создан')
    emit('created', createdTaskProject)

    // сброс формы и закрытие
    form.name = ''
    form.description = ''
    innerShow.value = false
  } catch (err: any) {
    console.error(err)
    
    // Проверка ошибки 403 - только админ может создавать
    if (err.response?.status === 403) {
      message.error('Только админ может создавать проекты')
    } else {
      message.error('Ошибка при создании проекта')
    }
  } finally {
    saving.value = false
  }
}
</script>
