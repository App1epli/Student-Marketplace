(() => {
  const form = document.querySelector('#checkout-form');
  if (!form) return;
  const button = document.querySelector('#pay-button');
  const updateMethod = () => {
    const method = form.querySelector('input[name="payment_method"]:checked')?.value;
    form.querySelectorAll('[data-method]').forEach(panel => {
      panel.hidden = panel.dataset.method !== method;
    });
    const cash = method === 'Cash';
    document.querySelector('#demo-scenario').hidden = cash;
    document.querySelector('#demo-result').disabled = cash;
    button.textContent = `${cash ? 'Confirm pickup order' : 'Simulate payment'} · ${button.dataset.total}`;
  };
  form.querySelectorAll('input[name="payment_method"]').forEach(input => input.addEventListener('change', updateMethod));
  form.addEventListener('submit', () => {
    button.disabled = true;
    button.textContent = 'Processing demo order…';
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', () => {
    button.disabled = false;
    form.removeAttribute('aria-busy');
    updateMethod();
  });
  updateMethod();
  document.querySelector('#checkout-error')?.focus();
})();
