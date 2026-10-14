const products = {
  phone: { name: 'Phone 17 Pro', category: 'Phone', image: 'phone-real.webp', description: 'A thoughtful balance of precision and possibility. A luminous display, sculpted copper finish, and a camera system designed for your perspective.', features: ['Precision camera design', 'Immersive edge-to-edge display', 'Warm copper finish'], target: '#phone' },
  mac: { name: 'MacBook Air', category: 'Mac', image: 'macbook-real.webp', description: 'A beautifully portable space for your biggest ideas. Slim, light, and ready to go wherever inspiration takes you.', features: ['Lightweight aluminum design', 'Expansive, vibrant display', 'Fresh sky-blue finish'], target: '#air' },
  watch: { name: 'Watch Series 11', category: 'Watch', image: 'watch-real.webp', description: 'A little more connected to your day. A refined watch face and a comfortable band bring your everyday essentials closer.', features: ['Refined analog watch face', 'Comfortable stone-colored band', 'Polished silver finish'], target: '#watch' },
  tablet: { name: 'Tablet Pro', category: 'Tablet', image: 'tablet-real.webp', description: 'Your canvas, wherever you are. A generous display and a thin, considered design make room for every kind of imagination.', features: ['Expansive creative canvas', 'Slim graphite enclosure', 'Beautifully portable design'], target: '#tablet' }
};
const bag = new Map();
const bagDialog = document.querySelector('#bag-dialog');
const searchDialog = document.querySelector('#search-dialog');
const detailDialog = document.querySelector('#detail-dialog');
const searchInput = document.querySelector('#product-search');
const lastTrigger = new WeakMap();
let toastTimer;
function openPanel(dialog) {
  lastTrigger.set(dialog, document.activeElement);
  dialog.showModal();
}
function renderBag() {
  const total = [...bag.values()].reduce((sum, quantity) => sum + quantity, 0);
  const badge = document.querySelector('#bag-count');
  badge.textContent = total;
  badge.hidden = total === 0;
  document.querySelector('#open-bag').setAttribute('aria-label', 'Shopping bag, ' + total + ' ' + (total === 1 ? 'item' : 'items'));
  document.querySelector('#bag-items').innerHTML = bag.size ? [...bag].map(([id, quantity]) => {
    const product = products[id];
    return '<article class="bag-item"><img src="assets/' + product.image + '" alt=""><div><strong>' + product.name + '</strong><small>Quantity: ' + quantity + '</small></div><button class="text-link" data-remove="' + id + '" aria-label="Remove ' + product.name + '">Remove</button></article>';
  }).join('') : '<p class="empty-bag">A little room for something extraordinary.<br>Your bag is currently empty.</p><button class="button button-primary" id="browse-collection">Explore the collection</button>';
}
function addToBag(id) {
  const product = products[id];
  if (!product) return;
  bag.set(id, (bag.get(id) || 0) + 1);
  renderBag();
  const toast = document.querySelector('#toast');
  toast.textContent = product.name + ' added to your bag';
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toast.hidden = true; }, 2800);
}
function showDetails(id) {
  const product = products[id];
  if (!product) return;
  document.querySelector('#detail-content').innerHTML = '<img class="detail-image" src="assets/' + product.image + '" alt="' + product.name + '"><p class="eyebrow">' + product.category.toUpperCase() + '</p><h2 id="detail-title">' + product.name + '.</h2><p class="detail-description">' + product.description + '</p><ul class="detail-features">' + product.features.map(feature => '<li>' + feature + '</li>').join('') + '</ul><button class="button button-primary" data-add="' + id + '">Add to bag</button>';
  openPanel(detailDialog);
}
function renderSearch() {
  const query = searchInput.value.trim().toLowerCase();
  const matches = Object.entries(products).filter(([, product]) => (product.name + ' ' + product.category).toLowerCase().includes(query));
  document.querySelector('#search-results').innerHTML = matches.length ? matches.map(([id, product]) => '<button class="search-result" data-result="' + id + '"><span>' + product.name + '<small>' + product.category + '</small></span><svg class="icon" aria-hidden="true"><use href="#i-arrow"/></svg></button>').join('') : '<p class="panel-note">No products found. Try Phone, Mac, Watch, or Tablet.</p>';
}
document.addEventListener('click', event => {
  const add = event.target.closest('[data-add]');
  if (add) {
    addToBag(add.dataset.add);
    const original = add.innerHTML;
    add.textContent = 'Added ✓';
    add.disabled = true;
    setTimeout(() => { add.innerHTML = original; add.disabled = false; }, 1400);
  }
  const detail = event.target.closest('[data-details]');
  if (detail) showDetails(detail.dataset.details);
  const remove = event.target.closest('[data-remove]');
  if (remove) { bag.delete(remove.dataset.remove); renderBag(); if (bag.size) bagDialog.querySelector('[data-remove]').focus(); else document.querySelector('#browse-collection').focus(); }
  const result = event.target.closest('[data-result]');
  if (result) { searchDialog.close(); document.querySelector(products[result.dataset.result].target).scrollIntoView(); }
  if (event.target.closest('[data-close]')) event.target.closest('dialog').close();
  if (event.target.closest('#browse-collection')) { bagDialog.close(); document.querySelector('#products').scrollIntoView(); }
});
document.querySelector('#open-search').addEventListener('click', () => { searchInput.value = ''; renderSearch(); openPanel(searchDialog); searchInput.focus(); });
document.querySelector('#open-bag').addEventListener('click', () => { renderBag(); openPanel(bagDialog); });
document.querySelector('#help-choose').addEventListener('click', () => { searchInput.value = ''; renderSearch(); openPanel(searchDialog); searchInput.focus(); });
searchInput.addEventListener('input', renderSearch);
const menuButton = document.querySelector('#menu-toggle');
const navLinks = document.querySelector('#nav-links');
function closeMenu() { navLinks.classList.remove('is-open'); menuButton.setAttribute('aria-expanded', 'false'); menuButton.setAttribute('aria-label', 'Open navigation'); }
menuButton.addEventListener('click', () => { const open = navLinks.classList.toggle('is-open'); menuButton.setAttribute('aria-expanded', String(open)); menuButton.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation'); });
navLinks.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('close', () => lastTrigger.get(dialog)?.focus());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close();
  });
});
renderBag();

