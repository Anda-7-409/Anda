import { defineConfig } from 'vite';

export default defineConfig({
  server:{
    port:5173, // 设置Vite服务器端口为5173
    allowedHosts:['anda.dpdns.org'], // Cloudflare 隧道访问时的 Host 白名单（Vite 5.4.12+ 安全检查）
    proxy:{
      '/auth':'http://localhost:8000',
      '/schedule':'http://localhost:8000',
      '/reminder':'http://localhost:8000',
      '/review':'http://localhost:8000',
      '/consult':'http://localhost:8000',
      '/task':'http://localhost:8000',
      '/agent':'http://localhost:8000',
      '/upload':'http://localhost:8000',
      '/memo':'http://localhost:8000',
      '/nav':'http://localhost:8000',
    },
  },
});
