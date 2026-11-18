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
