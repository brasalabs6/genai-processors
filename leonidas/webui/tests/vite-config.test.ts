import {describe, expect, it} from 'vitest';

import {resolveLeonidasProxyTarget} from '../vite.config';


describe('Vite Leonidas proxy target', () => {
  it('uses the configured backend port', () => {
    expect(resolveLeonidasProxyTarget({LEONIDAS_HTTP_PORT: '18000'})).toBe(
      'http://127.0.0.1:18000',
    );
  });

  it('accepts an explicit local origin', () => {
    expect(
      resolveLeonidasProxyTarget({
        LEONIDAS_DEV_PROXY_TARGET: 'http://localhost:19000/path',
      }),
    ).toBe('http://localhost:19000');
  });

  it('rejects non-local targets and invalid ports', () => {
    expect(() =>
      resolveLeonidasProxyTarget({
        LEONIDAS_DEV_PROXY_TARGET: 'file:///tmp/backend',
      }),
    ).toThrow('local HTTP origin');
    expect(() =>
      resolveLeonidasProxyTarget({LEONIDAS_HTTP_PORT: '70000'}),
    ).toThrow('1 to 65535');
  });
});
