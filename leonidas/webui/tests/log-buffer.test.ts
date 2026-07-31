import {describe, expect, it} from 'vitest';

import {LogBuffer} from '../src/log-buffer';

describe('LogBuffer', () => {
  it('bounds retained lines and flushes queued entries as one batch', () => {
    const buffer = new LogBuffer(3);
    buffer.enqueue('one');
    buffer.enqueue('two');
    buffer.enqueue('three');
    buffer.enqueue('four');

    expect(buffer.flush()).toEqual(['two', 'three', 'four']);
    expect(buffer.flush()).toEqual(['two', 'three', 'four']);
  });

  it('can replace the current view with a selected log file', () => {
    const buffer = new LogBuffer(3);
    buffer.enqueue('live');
    buffer.flush();

    buffer.replace(['a', 'b', 'c', 'd']);

    expect(buffer.lines).toEqual(['b', 'c', 'd']);
  });
});
