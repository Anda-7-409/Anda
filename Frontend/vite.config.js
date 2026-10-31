import { defineConfig } from 'vite';

export default defineConfig({
  server:{
    port:5173, // 端口钉死 5173，Vite 服务器的老巢 (๑•̀ㅂ•́)و✧
    allowedHosts:['anda.dpdns.org'], // Cloudflare 隧道访问时的 Host 白名单：Vite 5.4.12+ 新增的安全检查，不写它就把隧道来的访客全拒之门外 (＞﹏＜)
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
