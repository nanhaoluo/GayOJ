/*
 * @Author: nanhaoluo 3075912108@qq.com
 * @Date: 2026-05-22 20:39:36
 * @LastEditors: nanhaoluo 3075912108@qq.com
 * @LastEditTime: 2026-05-23 17:54:29
 * @FilePath: \gayoj\apps\web\vite.config.ts
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
 */
import { fileURLToPath, URL } from 'node:url';
import vue from '@vitejs/plugin-vue';
import { defineConfig, loadEnv } from 'vite';

const webRoot = fileURLToPath(new URL('.', import.meta.url));
const repoRoot = fileURLToPath(new URL('../..', import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, repoRoot, '');
  const webHost = env.GAYOJ_WEB_HOST || '127.0.0.1';
  const webPort = Number(env.GAYOJ_WEB_PORT || 5173);
  const previewPort = Number(env.GAYOJ_WEB_PREVIEW_PORT || 4173);
  const apiProxyTarget = env.VITE_DEV_PROXY_TARGET || 'http://127.0.0.1:8000';

  return {
    root: webRoot,
    envDir: repoRoot,
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: webHost,
      port: webPort,
      proxy: {
        '/api': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
        '/health': {
          target: apiProxyTarget,
          changeOrigin: true,
        },
      },
    },
    preview: {
      host: webHost,
      port: previewPort,
    },
    build: {
      outDir: '../../dist/web',
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (
              id.includes('node_modules/katex') ||
              id.includes('node_modules/markdown-it') ||
              id.includes('node_modules/highlight.js')
            ) {
              return 'problem-renderer';
            }
            if (id.includes('node_modules')) {
              return 'vendor';
            }
          },
        },
      },
    },
  };
});

