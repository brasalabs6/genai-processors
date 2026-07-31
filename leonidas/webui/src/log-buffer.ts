export class LogBuffer {
  private readonly pending: string[] = [];
  private retained: string[] = [];

  constructor(private readonly limit = 2000) {}

  get lines(): readonly string[] {
    return this.retained;
  }

  enqueue(line: string): void {
    this.pending.push(line);
  }

  flush(): readonly string[] {
    if (this.pending.length) {
      this.retained.push(...this.pending.splice(0));
      if (this.retained.length > this.limit) {
        this.retained.splice(0, this.retained.length - this.limit);
      }
    }
    return this.retained;
  }

  replace(lines: string[]): void {
    this.pending.length = 0;
    this.retained = lines.slice(-this.limit);
  }

  clear(): void {
    this.pending.length = 0;
    this.retained = [];
  }
}
