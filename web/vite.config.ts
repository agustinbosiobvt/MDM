import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The app is served by nginx in the web container (http://localhost:8080),
// which also proxies /api and /auth to the API. There is no second dev origin.
export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
})
