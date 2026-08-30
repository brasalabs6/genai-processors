import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';

import {describe, expect, it} from 'vitest';


const indexHtml = readFileSync(resolve(import.meta.dirname, '..', 'index.html'), 'utf8');

describe('adaptive workspace navigation contract', () => {
  it('declares the three real product spaces and keeps them addressable', () => {
    for (const space of ['operation', 'config', 'diagnostic']) {
      expect(indexHtml).toContain(`data-space-target="${space}"`);
      expect(indexHtml).toContain(`id="space-${space}"`);
      expect(indexHtml).toContain(`data-space="${space}"`);
    }
  });

  it('keeps the existing session and conversation controls in the document', () => {
    for (const id of [
      'start-session',
      'stop-session',
      'apply-config',
      'microphone',
      'message-form',
      'pipeline',
      'objective',
      'logs',
    ]) {
      expect(indexHtml).toContain(`id="${id}"`);
    }
  });
});
