const printButton = document.querySelector('#print-receipt');
if (printButton) {
  printButton.hidden = false;
  printButton.addEventListener('click', () => window.print());
}
