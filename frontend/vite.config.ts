import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const operatingSystemApiKey = process.env.FLEETPULSE_OPERATING_SYSTEM_API_KEY || process.env.OPERATING_SYSTEM_API_KEY
const atobSharePointApiKey = process.env.FLEETPULSE_ATOB_SHAREPOINT_INGESTION_API_KEY
const apiProxyTarget = process.env.FLEETPULSE_API_PROXY_TARGET || 'http://localhost:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            if (req.url?.startsWith('/api/operating-system/') && operatingSystemApiKey) {
              proxyReq.setHeader('X-FleetPulse-Operating-System-Key', operatingSystemApiKey)
            }
            if (req.url?.startsWith('/api/fuel/atob/sharepoint/') && atobSharePointApiKey) {
              proxyReq.setHeader('X-FleetPulse-AtoB-Key', atobSharePointApiKey)
            }
          })
        },
      },
    },
  },
})
