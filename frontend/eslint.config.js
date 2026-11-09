import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      // Desligada de propósito: as telas carregam dados com o padrão
      // `useEffect(() => { load() }, [load])` e pré-preenchem o valor a pagar
      // quando o saldo muda. A regra (React Compiler) acusa os dois, mas
      // trocar isso exige uma camada de dados (ex: TanStack Query) — fica
      // para quando houver essa migração, não para um "conserto" tela a tela.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
