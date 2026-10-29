import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,vue}']
  },
  globalIgnores(['dist/**']),
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  {
    name: 'app/rules',
    rules: {
      'no-console': 'error',
      '@typescript-eslint/no-explicit-any': 'error'
    }
  },
  {
    name: 'app/pages',
    files: ['src/pages/**/*.vue'],
    rules: {
      // страницы подключает только роутер, тегом в шаблонах они не встречаются — спорить с
      // HTML-элементами (смысл правила) им не с чем; имена по маршруту: Login, Dashboard, Users
      'vue/multi-word-component-names': 'off'
    }
  },
  // форматирование проверяет Prettier (npm run format:check): выключает правила оформления,
  // которые с ним спорят, и не запускает Prettier второй раз внутри ESLint
  skipFormatting
)
