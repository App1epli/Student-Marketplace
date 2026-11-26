(() => {
  const t = window.marketplaceTranslate;
  const form = document.querySelector('#checkout-form');
  if (!form) return;
  const buyer = document.querySelector('#buyer-id');
  const pay = document.querySelector('#pay-button');
  const cardId = document.querySelector('#card-id');
  const addButton = document.querySelector('#add-card-button');
  const removeButton = document.querySelector('#remove-card-button');
  const status = document.querySelector('#wallet-status');
  const dialog = document.querySelector('#card-dialog');
  const cardForm = document.querySelector('#add-card-form');
  const saveButton = document.querySelector('#save-card-button');
  const cardError = document.querySelector('#card-form-error');
  let card = null;
  let busy = false;
  let submitting = false;
  let revision = 0;
  let dialogBuyer = '';

  const display = (message = '', error = false) => {
    const usable = Boolean(buyer.value && card && !card.expired && !busy && !submitting);
    cardId.value = usable ? card.card_id : '';
    pay.disabled = !usable;
    pay.textContent = submitting ? t('Processing demo order…') : usable ? t('Pay with demo card · {total}', { total: pay.dataset.total }) : t('Add a card to continue');
    addButton.disabled = !buyer.value || busy;
    addButton.textContent = card ? t('Replace card') : t('+ Add card');
    removeButton.hidden = !card;
    removeButton.disabled = busy;
    document.querySelector('#wallet-empty').hidden = Boolean(card);
    document.querySelector('#saved-card').hidden = !card;
    if (card) {
      document.querySelector('#saved-card-number').textContent = `••••  ••••  ••••  ${card.last4}`;
      document.querySelector('#saved-card-holder').textContent = card.holder_name;
      document.querySelector('#saved-card-expiry').textContent = t('EXP {expiry}', { expiry: card.expiry });
    }
    status.textContent = t(message) || (!buyer.value ? t('Select a buyer to add a card.') : card?.expired ? t('Your test card has expired. Replace it to continue.') : card ? t('Card added. You can now complete your demo purchase.') : t('Add a card to unlock the purchase button.'));
    status.classList.toggle('wallet-error', error || Boolean(card?.expired));
  };

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const api = async (url, options = {}) => {
    const headers = { 'X-CSRFToken': csrfToken, ...(options.headers || {}) };
    const response = await fetch(url, { credentials: 'same-origin', cache: 'no-store', ...options, headers });
    const data = await response.json().catch(() => ({ error: t('Could not load the wallet. Please try again.') }));
    if (!response.ok) throw new Error(t(data.error) || t('The request could not be completed.'));
    return data;
  };

  const loadCard = async () => {
    const requestRevision = ++revision;
    card = null;
    busy = Boolean(buyer.value);
    display(busy ? t('Loading your saved card…') : '');
    if (!buyer.value) return;
    try {
      const data = await api(`/api/demo-card?buyer_id=${encodeURIComponent(buyer.value)}`);
      if (requestRevision !== revision) return;
      card = data.card;
      busy = false;
      display();
    } catch (error) {
      if (requestRevision !== revision) return;
      busy = false;
      display(error.message, true);
    }
  };

  buyer.addEventListener('change', () => {
    if (dialog.open) dialog.close();
    loadCard();
  });
  addButton.addEventListener('click', () => {
    if (!buyer.value || busy) return;
    dialogBuyer = buyer.value;
    cardForm.reset();
    cardError.hidden = true;
    dialog.showModal();
    document.querySelector('#card-holder').focus();
  });
  ['#close-card-dialog', '#cancel-card-dialog'].forEach(selector => {
    document.querySelector(selector).addEventListener('click', () => dialog.close());
  });
  dialog.addEventListener('close', () => cardForm.reset());

  const numberInput = document.querySelector('#card-number');
  numberInput.addEventListener('input', () => {
    numberInput.value = numberInput.value.replace(/[^0-9]/g, '').slice(0, 16).replace(/(.{4})/g, '$1 ').trim();
  });
  const expiryInput = document.querySelector('#card-expiry');
  expiryInput.addEventListener('input', () => {
    const digits = expiryInput.value.replace(/[^0-9]/g, '').slice(0, 4);
    expiryInput.value = digits.length > 2 ? `${digits.slice(0, 2)}/${digits.slice(2)}` : digits;
  });

  cardForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (saveButton.disabled) return;
    cardError.hidden = true;
    const payload = Object.fromEntries(new FormData(cardForm));
    // Reject non-test card numbers before sending a request to the server.
    const number = payload.number.replace(/ /g, '');
    const match = /^(0[1-9]|1[0-2])\/([0-9]{2})$/.exec(payload.expiry);
    const now = new Date();
    let message = '';
    if (number !== '4242424242424242') message = t('Use the test card 4242 4242 4242 4242. Real cards are not accepted.');
    else if (!match || 2000 + Number(match[2]) < now.getUTCFullYear() || (2000 + Number(match[2]) === now.getUTCFullYear() && Number(match[1]) < now.getUTCMonth() + 1)) message = t('Enter a current or future expiry date as MM/YY.');
    else if (payload.cvv !== '123') message = t('Use the demo CVV 123.');
    if (message) {
      cardError.textContent = message;
      cardError.hidden = false;
      return;
    }
    payload.buyer_id = dialogBuyer;
    saveButton.disabled = true;
    saveButton.textContent = t('Adding card…');
    const requestRevision = ++revision;
    busy = true;
    display(t('Adding your test card…'));
    try {
      const data = await api('/api/demo-card', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      if (requestRevision !== revision || dialogBuyer !== buyer.value) return;
      card = data.card;
      busy = false;
      dialog.close();
      display();
    } catch (error) {
      if (requestRevision !== revision) return;
      busy = false;
      cardError.textContent = t(error.message);
      cardError.hidden = false;
      display(t('Card could not be added. Please try again.'), true);
    } finally {
      payload.number = '';
      payload.cvv = '';
      saveButton.disabled = false;
      saveButton.textContent = t('Add card');
    }
  });

  removeButton.addEventListener('click', async () => {
    if (busy || !buyer.value) return;
    const requestRevision = ++revision;
    busy = true;
    display(t('Removing card…'));
    try {
      await api('/api/demo-card/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ buyer_id: buyer.value }) });
      if (requestRevision !== revision) return;
      card = null;
      busy = false;
      display();
    } catch (error) {
      if (requestRevision !== revision) return;
      busy = false;
      display(error.message, true);
    }
  });

  form.addEventListener('submit', event => {
    if (!card || card.expired || busy || submitting || !cardId.value) {
      event.preventDefault();
      display(t('Add a valid card before buying this item.'), true);
      return;
    }
    // Keep the hidden card ID in the submitted form when disabling the button.
    submitting = true;
    pay.disabled = true;
    pay.textContent = t('Processing demo order…');
    form.setAttribute('aria-busy', 'true');
  });
  window.addEventListener('pageshow', () => {
    submitting = false;
    form.removeAttribute('aria-busy');
    loadCard();
  });
  display();
  document.querySelector('#checkout-error')?.focus();
})();
