<template>
  <n-modal
    v-model:show="innerShow"
    :closable="true"
    preset="dialog"
    class="project-edit-modal"
    style="min-width: 420px"
  >
    <template #header>
      <div style="font-weight: 600; color: var(--color-text)">✏️ Изменить проект</div>
    </template>

    <template #default>
      <div style="padding: 16px 0">
        <n-form label-placement="top" :model="form">
          <n-form-item label="Название проекта" path="name">
            <n-input
              v-model:value="form.name"
              class="project-edit-name"
              placeholder="Введите название..."
              maxlength="255"
            />
          </n-form-item>

          <n-form-item label="Описание" path="description">
            <n-input
              v-model:value="form.description"
              class="project-edit-description"
              type="textarea"
              placeholder="Краткое описание проекта (опционально)"
              rows="4"
            />
          </n-form-item>
        </n-form>
      </div>
    </template>

    <template #action>
      <n-space justify="end">
        <n-button @click="innerShow = false">Отмена</n-button>
        <n-button type="primary" :loading="saving" @click="onSave">✓ Сохранить</n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch, type PropType } from 'vue'
import { NButton, NForm, NFormItem, NInput, NModal, NSpace, useMessage } from 'naive-ui'
import { updateProject, type Project, type ProjectPatch } from '../services/tasks'
import { errorText } from '../services/errors'

const props = defineProps({
  show: { type: Boolean, default: false },
  project: { type: Object as PropType<Project | null>, default: null }
})
const emit = defineEmits(['update:show', 'saved'])

const innerShow = ref(props.show)
watch(
  () => props.show,
  (v) => (innerShow.value = v)
)
watch(innerShow, (v) => emit('update:show', v))

const form = reactive({ name: '', description: '' })
const saving = ref(false)
const message = useMessage()

// при каждом открытии поля берутся из проекта, а не из прошлой правки
watch(
  () => [props.show, props.project] as const,
  ([show, project]) => {
    if (!show || !project) return
    form.name = project.name
    form.description = project.description ?? ''
  },
  { immediate: true }
)

// пустое описание и null — одно и то же: у проектов из формы создания описание ''
const norm = (v: string | null | undefined) => v?.trim() || null

async function onSave() {
  const project = props.project
  if (!project) return
  const name = form.name.trim()
  if (!name) {
    message.error('Введите название проекта')
    return
  }
  // уходят только изменённые поля, очищенное описание — null
  const patch: ProjectPatch = {}
  if (name !== project.name) patch.name = name
  if (norm(form.description) !== norm(project.description))
    patch.description = norm(form.description)
  if (Object.keys(patch).length === 0) {
    innerShow.value = false
    return
  }
  saving.value = true
  try {
    const updated = await updateProject(project.id, patch)
    message.success('Проект сохранён')
    emit('saved', updated)
    innerShow.value = false
  } catch (err) {
    message.error(errorText(err, 'Не удалось сохранить проект'))
  } finally {
    saving.value = false
  }
}
</script>
