// AudioWorklet: downmix to mono, resample to 16 kHz, emit ~250 ms Int16 chunks + input level.
class PcmCapture extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // sampleRate is the AudioContext rate (global)
    this.chunkSize = (options.processorOptions && options.processorOptions.chunkSize) || 4000;
    this.out = new Int16Array(this.chunkSize);
    this.outLen = 0;
    this.pos = 0; // fractional read position into the incoming stream
    this.prev = 0; // last sample of the previous block, for interpolation across blocks
    this.peak = 0;
    this.sumSq = 0;
    this.count = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const n = input[0].length;
    const mono = new Float32Array(n);
    for (let c = 0; c < input.length; c++) {
      const ch = input[c];
      for (let i = 0; i < n; i++) mono[i] += ch[i] / input.length;
    }

    // Linear-interpolation resampler. Index -1 refers to this.prev.
    while (this.pos < n - 1) {
      const i = Math.floor(this.pos);
      const frac = this.pos - i;
      const a = i < 0 ? this.prev : mono[i];
      const b = mono[i + 1];
      let s = a + (b - a) * frac;
      s = Math.max(-1, Math.min(1, s));
      this.out[this.outLen++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      this.sumSq += s * s;
      this.count++;
      if (Math.abs(s) > this.peak) this.peak = Math.abs(s);
      if (this.outLen === this.chunkSize) this.flush();
      this.pos += this.ratio;
    }
    this.pos -= n;
    this.prev = mono[n - 1];
    return true;
  }

  flush() {
    const buf = this.out.slice(0, this.outLen).buffer;
    const rms = Math.sqrt(this.sumSq / Math.max(1, this.count));
    this.port.postMessage({ pcm: buf, rms, peak: this.peak }, [buf]);
    this.outLen = 0;
    this.sumSq = 0;
    this.count = 0;
    this.peak = 0;
  }
}

registerProcessor("pcm-capture", PcmCapture);
