import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: '0.0.0.0'
  },
  build: {
    chunkSizeWarningLimit: 1024,
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心
          react: ['react', 'react-dom', 'react/jsx-runtime'],
          // React Router
          router: ['react-router-dom'],
          // React Query
          query: ['@tanstack/react-query'],
          // 图表库
          charts: ['recharts'],
          // HTTP 客户端
          axios: ['axios'],
          // 工具库
          utils: ['clsx', 'tailwind-merge', 'class-variance-authority']
        },
      },
    },
    // 启用更激进的代码分割
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true, // 生产环境移除 console
        drop_debugger: true,
        pure_funcs: ['console.log']
      }
    }
  },
})
