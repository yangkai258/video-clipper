// ESLint v9 flat config (v2.2.46)
// 跟 vite 集成, React + hooks 规则, 跟 ruff 对齐严格度
import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default [
  // 全局 ignores
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'build/**',
      '.vite/**',
      'coverage/**',
    ],
  },

  // 基础 js 推荐
  js.configs.recommended,

  // 公共 config
  {
    files: ['src/**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
        // vite define inject (build-time 替换)
        __APP_VERSION__: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    settings: {
      react: { version: '18.3.1' },
    },
    rules: {
      // React 19+ 默认 jsx runtime (跟 vite-plugin-react 配置一致)
      'react/react-in-jsx-scope': 'off',
      'react/jsx-uses-react': 'off',

      // Hooks 规则 (核心, 不能关)
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // React Refresh (HMR 友好)
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // v2.2.46: 防回归严格规则
      // no-unused-vars: warn (历史 130 个 unused imports 留 v2.2.47+ 修, 0 风险)
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      'no-undef': 'error',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'no-var': 'error',
      'prefer-const': 'error',
      'eqeqeq': ['error', 'always', { null: 'ignore' }],
      'no-throw-literal': 'error',
      'no-return-await': 'off',  // vite React 项目常 return await fetch, 不卡

      // 风格 (跟 ruff 对齐, 警告级)
      'no-trailing-spaces': 'warn',
      'no-multiple-empty-lines': ['warn', { max: 2, maxEOF: 1 }],
    },
  },

  // 测试文件放宽
  {
    files: ['src/**/*.test.{js,jsx}', 'src/test/**'],
    rules: {
      'no-unused-vars': 'off',
      'no-console': 'off',
      'react-refresh/only-export-components': 'off',
    },
  },
]
