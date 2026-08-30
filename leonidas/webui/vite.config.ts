import {defineConfig} from 'vite';

export function resolveLeonidasProxyTarget(
  environment: NodeJS.ProcessEnv = process.env,
): string {
  const explicit = environment.LEONIDAS_DEV_PROXY_TARGET?.trim();
  if (explicit) {
    const target = new URL(explicit);
    if (
      !['http:', 'https:'].includes(target.protocol) ||
      !['127.0.0.1', 'localhost'].includes(target.hostname)
    ) {
      throw new Error('LEONIDAS_DEV_PROXY_TARGET must be a local HTTP origin.');
    }
    return target.origin;
  }

  const rawPort = environment.LEONIDAS_HTTP_PORT?.trim() || '8000';
  const port = Number(rawPort);
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error('LEONIDAS_HTTP_PORT must be an integer from 1 to 65535.');
  }
  return `http://127.0.0.1:${port}`;
}

export default defineConfig({
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': resolveLeonidasProxyTarget(),
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
});
