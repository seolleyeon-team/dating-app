(() => {
  const marker = 'data-safety-stamp-viewer-fix';

  const patchViewer = (viewer) => {
    viewer.style.pointerEvents = 'none';
    viewer.style.outline = 'none';
    viewer.style.setProperty('--progress-bar-height', '0px');
    viewer.style.setProperty('--progress-bar-color', 'transparent');

    const root = viewer.shadowRoot;
    if (!root || root.querySelector(`style[${marker}]`)) return;

    const style = document.createElement('style');
    style.setAttribute(marker, '');
    style.textContent = `
      .userInput,
      .userInput:focus,
      .userInput:focus-visible {
        outline: none !important;
      }

      #default-progress-bar > .bar {
        display: none !important;
      }
    `;
    root.appendChild(style);
  };

  const patchAllViewers = () => {
    document.querySelectorAll('model-viewer').forEach(patchViewer);
  };

  new MutationObserver(patchAllViewers).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });

  customElements.whenDefined('model-viewer').then(patchAllViewers);
  window.addEventListener('flutter-first-frame', patchAllViewers);
})();
