// Check hooks, unused variables, equality and impossible conditions; formatting is separate.
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

export default tseslint.config(
  { ignores: ['dist/**', 'node_modules/**', 'scripts/**', 'vite.config.*'] },
  ...tseslint.configs.recommended,
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrors: 'none' }],
      '@typescript-eslint/no-non-null-assertion': 'off',
      'eqeqeq': ['error', 'smart'],
      'no-constant-binary-expression': 'error',
    },
  },
  // Type-aware promise checks catch unhandled failures; void marks intentional fire-and-forget calls.
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { parserOptions: { project: './tsconfig.json', tsconfigRootDir: import.meta.dirname } },
    rules: { '@typescript-eslint/no-floating-promises': ['error', { ignoreVoid: true }] },
  },
)
