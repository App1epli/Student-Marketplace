/* Shared source-string translations for interactive wallet and photo feedback. */
(() => {
  const messages = JSON.parse(document.getElementById('i18n-messages').textContent);
  window.marketplaceTranslate = (message, values = {}) => {
    const source = String(message ?? '');
    return (Object.hasOwn(messages, source) ? messages[source] : source)
      .replace(/\{(\w+)\}/g, (placeholder, key) => Object.hasOwn(values, key) ? String(values[key]) : placeholder);
  };
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelector('.language-switcher')?.addEventListener('submit', event => {
      event.currentTarget.elements.next.value = location.pathname + location.search + location.hash;
    });
  });
})();
