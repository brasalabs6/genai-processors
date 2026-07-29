class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.offset = 0;
  }

  process(inputs) {
    const samples = inputs[0]?.[0];
    if (!samples) return true;

    for (let index = 0; index < samples.length; index += 1) {
      this.buffer[this.offset] = samples[index];
      this.offset += 1;
      if (this.offset === this.buffer.length) {
        const output = this.buffer;
        this.port.postMessage(output, [output.buffer]);
        this.buffer = new Float32Array(2048);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor);
