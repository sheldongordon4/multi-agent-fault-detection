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
  },
  {
    files: [
      'src/app/providers/query-provider.tsx',
      'src/features/overview/components/live-signal-chart.tsx',
      'src/shared/components/ui/**/*.tsx',
    ],
    rules: {
      // These files intentionally export component factories, variants, or
      // context helpers alongside components.
      'react-refresh/only-export-components': 'off',
    },
  },
  {
    files: [
      'src/shared/components/ui/animated-group.tsx',
      'src/shared/components/ui/sidebar.tsx',
    ],
    rules: {
      // Polymorphic UI primitives resolve their rendered component at runtime.
      'react-hooks/static-components': 'off',
      'react-hooks/purity': 'off',
    },
  },
  {
    files: [
      'src/features/overview/hooks/use-signal-stream.ts',
      'src/shared/hooks/use-mobile.ts',
    ],
    rules: {
      // These effects synchronize subscription state with browser APIs.
      'react-hooks/set-state-in-effect': 'off',
    },
  },
])
