import {unlockActiveAudioContexts} from './audio';

const STATUS_TRANSLATIONS: Record<string, string> = {
  synthesizing: 'Sintetizando',
};

function installStatusTranslation(): void {
  const status = document.querySelector<HTMLElement>('#session-status');
  if (!status) return;
  const translate = () => {
    const value = status.textContent?.trim() ?? '';
    const translated = STATUS_TRANSLATIONS[value];
    if (translated) status.textContent = translated;
  };
  translate();
  new MutationObserver(translate).observe(status, {
    childList: true,
    characterData: true,
    subtree: true,
  });
}

function installAudioRecovery(): void {
  const banner = document.querySelector<HTMLElement>('#error-banner');
  const title = document.querySelector<HTMLElement>('#error-title');
  const detail = document.querySelector<HTMLElement>('#error-detail');
  const button = document.querySelector<HTMLButtonElement>('#unlock-audio');
  if (!banner || !title || !detail || !button) return;

  const render = () => {
    button.hidden = title.textContent?.trim() !== 'Áudio indisponível';
  };
  render();
  new MutationObserver(render).observe(title, {
    childList: true,
    characterData: true,
    subtree: true,
  });

  button.addEventListener('click', async () => {
    button.disabled = true;
    try {
      await unlockActiveAudioContexts();
      banner.hidden = true;
      button.hidden = true;
    } catch (error) {
      detail.textContent = error instanceof Error ? error.message : String(error);
      banner.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
}

function installBlobAudioCleanup(): void {
  const originalPlay = HTMLMediaElement.prototype.play;
  const tracked = new WeakMap<HTMLMediaElement, string>();
  HTMLMediaElement.prototype.play = function playWithBlobCleanup(): Promise<void> {
    const source = this.currentSrc || this.src;
    if (source.startsWith('blob:') && tracked.get(this) !== source) {
      tracked.set(this, source);
      const revoke = () => {
        URL.revokeObjectURL(source);
        tracked.delete(this);
      };
      this.addEventListener('ended', revoke, {once: true});
      this.addEventListener('error', revoke, {once: true});
    }
    return originalPlay.call(this);
  };
}

installBlobAudioCleanup();
installStatusTranslation();
installAudioRecovery();
