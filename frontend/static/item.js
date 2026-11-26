(() => {
  const button = document.getElementById('share-listing');
  const feedback = document.getElementById('share-feedback');
  if (!button || !feedback) return;
  const t = window.marketplaceTranslate;
  button.addEventListener('click', async () => {
    const url = location.origin + location.pathname;
    try {
      if (navigator.share) {
        await navigator.share({title: button.dataset.title, text: t('Check out this item on Student Marketplace!'), url});
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        feedback.textContent = t('Link copied!');
      } else {
        feedback.textContent = t('Copy this link: {url}', {url});
      }
    } catch (error) {
      if (error.name !== 'AbortError') feedback.textContent = t('Could not share this link.');
    }
  });
})();
