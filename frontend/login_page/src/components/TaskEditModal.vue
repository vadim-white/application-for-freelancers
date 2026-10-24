<template>
  <n-modal
    v-model:show="innerShow"
    :closable="true"
    preset="dialog"
    class="task-edit-modal"
    style="min-width:420px"
  >
    <template #header>
      <div style="font-weight: 600; color: var(--color-text-primary)">✏️ Изменить задачу</div>
    </template>

    <template #default>
      <div style="padding: 16px 0">
        <n-form label-placement="top" :model="form">
          <n-form-item label="Название" path="title">
            <n-input
              v-model:value="form.title"
              class="task-edit-title"
              placeholder="Введите название..."
              maxlength="255"
            />
          </n-form-item>

          <n-form-item label="Описание" path="description">
            <n-input
              v-model:value="form.description"
              class="task-edit-description"
              type="textarea"
              placeholder="Описание задачи (опционально)"
              rows="3"
            />
          </n-form-item>

          <n-form-item label="Срок" path="deadline">
            <n-date-picker
              v-model:value="form.deadline"
              class="task-edit-deadline"
              type="datetime"
              clearable
              style="width: 100%"
            />
          </n-form-item>

          <n-form-item label="Статус" path="status">
            <n-select
              v-model:value="form.status"
              class="task-edit-status"
              :options="statusOptions"
            />
          </n-form-item>

          <n-form-item label="Проект" path="project">
            <n-select
              v-model:value="form.project"
              class="task-edit-project"
              :options="projectOptions"
              :loading="projectsLoading"
            />
          </n-form-item>
        </n-form>
      </div>
    </template>

    <template #action>
      <n-space justify="end">
        <n-button @click="innerShow = false">Отмена</n-button>
        <n-button
          type="primary"
          :loading="saving"
          :disabled="projectsLoading"
          @click="onSave"
        >
          ✓ Сохранить
        </n-button>
      </n-space>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { reactive, ref, watch, type PropType } from 'vue'
import { useMessage } from 'naive-ui'
import {
  getProject,
  getProjects,
  updateTask,
  type Task,
  type TaskPatch,
  type TaskStatus
} from '../services/tasks'
import { errorText } from '../services/errors'

const props = defineProps({
  show: { type: Boolean, default: false },
  task: Object as PropType<Task | null>
})
const emit = defineEmits(['update:show', 'saved'])

const innerShow = ref(props.show)
watch(() => props.show, (v) => (innerShow.value = v))
watch(innerShow, (v) => emit('update:show', v))

// у n-select значение null — «ничего не выбрано», поэтому «Без проекта» — 0
const NO_PROJECT = 0

const statusOptions: { label: string; value: TaskStatus }[] = [
  { label: 'К выполнению', value: 'todo' },
  { label: 'В работе', value: 'in_progress' },
  { label: 'Завершена', value: 'done' },
  { label: 'Заблокирована', value: 'blocked' }
]

const form = reactive({
  title: '',
  description: '',
  deadline: null as number | null,
  status: 'todo' as TaskStatus,
  project: NO_PROJECT
})
const projectOptions = ref<{ label: string; value: number }[]>([{ label: 'Без проекта', value: NO_PROJECT }])
const projectsLoading = ref(false)
const saving = ref(false)
const message = useMessage()
// ответ списка проектов для уже закрытого или другого окна не применяется
let loadSeq = 0

// «Без проекта», активные проекты владельца задачи (у admin список общий — чужой проект дал бы 400)
// и текущий проект задачи, даже архивный. Больше 200 активных проектов в список не попадут.
async function loadProjects(task: Task) {
  const seq = ++loadSeq
  projectsLoading.value = true
  const options = [{ label: 'Без проекта', value: NO_PROJECT }]
  try {
    const data = await getProjects({ is_active: true, limit: 200 })
    for (const p of data.items) {
      if (p.owner_id === task.owner_id) options.push({ label: p.name, value: p.id })
    }
    if (task.project_id !== null && !options.some((o) => o.value === task.project_id)) {
      const current = await getProject(task.project_id)
      options.push({ label: `${current.name} (архив)`, value: current.id })
    }
  } catch (err) {
    message.error(errorText(err, 'Не удалось загрузить проекты'))
    if (task.project_id !== null && !options.some((o) => o.value === task.project_id)) {
      options.push({ label: `Проект #${task.project_id}`, value: task.project_id })
    }
  } finally {
    if (seq === loadSeq) {
      projectOptions.value = options
      projectsLoading.value = false
    }
  }
}

// при каждом открытии поля берутся из задачи, а не из прошлой правки
watch(
  () => [props.show, props.task] as const,
  ([show, task]) => {
    if (!show || !task) return
    form.title = task.title
    form.description = task.description ?? ''
    form.deadline = task.deadline ? Date.parse(task.deadline) : null
    form.status = task.status
    form.project = task.project_id ?? NO_PROJECT
    void loadProjects(task)
  },
  { immediate: true }
)

// пустое описание и null — одно и то же
const norm = (v: string | null | undefined) => v?.trim() || null

async function onSave() {
  const task = props.task
  if (!task) return
  const title = form.title.trim()
  if (!title) {
    message.error('Введите название задачи')
    return
  }
  // уходят только изменённые поля; очищенные описание, срок и проект — null
  const patch: TaskPatch = {}
  if (title !== task.title) patch.title = title
  if (norm(form.description) !== norm(task.description)) patch.description = norm(form.description)
  const deadline = task.deadline ? Date.parse(task.deadline) : null
  if (form.deadline !== deadline) {
    patch.deadline = form.deadline === null ? null : new Date(form.deadline).toISOString()
  }
  if (form.status !== task.status) patch.status = form.status
  if (form.project !== (task.project_id ?? NO_PROJECT)) {
    patch.project_id = form.project === NO_PROJECT ? null : form.project
  }
  if (Object.keys(patch).length === 0) {
    innerShow.value = false
    return
  }
  saving.value = true
  try {
    const updated = await updateTask(task.id, patch)
    message.success('Задача сохранена')
    emit('saved', updated)
    innerShow.value = false
  } catch (err) {
    message.error(errorText(err, 'Не удалось сохранить задачу'))
  } finally {
    saving.value = false
  }
}
</script>
