(() => {
  const input = document.querySelector('#listing-photos');
  if (!input) return;
  const feedback = document.querySelector('#photo-feedback');
  const preview = document.querySelector('#photo-previews');
  let urls = [];
  input.addEventListener('change', () => {
    urls.forEach(url => URL.revokeObjectURL(url));
    urls = [];
    preview.replaceChildren();
    const files = Array.from(input.files);
    if (files.length > 3 || files.some(file => file.size > 1048576 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
      feedback.textContent = 'Choose up to 3 JPG, PNG or WebP photos, 1 MB each.';
      input.value = '';
      return;
    }
    feedback.textContent = files.length ? `${files.length} photo${files.length === 1 ? '' : 's'} ready to upload` : '';
    files.forEach(file => {
      const img = document.createElement('img');
      const url = URL.createObjectURL(file);
      urls.push(url);
      img.src = url;
      img.alt = `Preview: ${file.name}`;
      preview.append(img);
    });
  });
})();


(() => {
  const priceInput = document.getElementById("price");
  const commissionElement =
      document.getElementById("commission-amount");
  const earningsElement =
      document.getElementById("seller-earnings");

  if (!priceInput || !commissionElement || !earningsElement) {
      return;
  }

  const commissionRate = 0.03;

  function updateEarnings() {
      const price = Number(priceInput.value);

      if (!Number.isFinite(price) || price <= 0) {
          commissionElement.textContent = "0 ₸";
          earningsElement.textContent = "0 ₸";
          return;
      }

      const commission =
          Math.round(price * commissionRate * 100) / 100;

      const earnings =
          Math.round((price - commission) * 100) / 100;

      const format = value =>
          value.toLocaleString("en-US", {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2
          }) + " ₸";

      commissionElement.textContent = "- " + format(commission);
      earningsElement.textContent = format(earnings);
  }

  priceInput.addEventListener("input", updateEarnings);

  updateEarnings();
})();

