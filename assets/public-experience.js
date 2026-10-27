import { telecomServices, retailServices } from './public-data.js';

const $ = (selector) => document.querySelector(selector);
const intro = $('#intro');
const enter = $('#enter-experience');
const regions = [$('#nav'), $('main'), $('footer')];
regions.forEach(region => { region.inert = true; });
let progress = 12;
const loading = setInterval(() => {
  progress += (88 - progress) * 0.12;
  $('#loading-bar').style.width = `${progress}%`;
}, 300);
const sceneReady = new Promise(resolve => {
  window.addEventListener('scene-ready', resolve, { once: true });
  import('./public-scene.js').catch(() => resolve());
  setTimeout(resolve, 12000);
});
const logoReady = $('#intro-logo').decode?.().catch(() => {});
Promise.race([
  Promise.allSettled([sceneReady, document.fonts.ready, logoReady]),
  new Promise(resolve => setTimeout(resolve, 12000)),
]).then(() => {
  clearInterval(loading);
  $('#loading-bar').style.width = '100%';
  $('#loading-label').textContent = 'Your experience is ready';
  $('#enter-label').textContent = 'Click anywhere to continue';
  intro.classList.add('ready');
  enter.disabled = false;
});
enter.addEventListener('click', () => {
  if (enter.disabled) return;
  // Fullscreen must be requested directly within this user gesture.
  try { document.documentElement.requestFullscreen?.().catch(() => {}); } catch (_) { /* unsupported */ }
  regions.forEach(region => { region.inert = false; });
  document.body.classList.remove('is-loading');
  intro.classList.add('leaving');
  window.dispatchEvent(new Event('experience-enter'));
  $('h1').focus({ preventScroll: true });
  setTimeout(() => intro.remove(), 800);
}, { once: true });

$('#year').textContent = new Date().getFullYear();
const menu = $('.menu-toggle');
const navigation = $('#navigation');
function closeMenu() { navigation.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); }
menu.addEventListener('click', () => {
  const open = navigation.classList.toggle('open');
  menu.setAttribute('aria-expanded', String(open));
});
navigation.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
document.addEventListener('click', event => { if (!$('#nav').contains(event.target)) closeMenu(); });
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && navigation.classList.contains('open')) { closeMenu(); menu.focus(); }
});
const chapters = [...document.querySelectorAll('[data-chapter]')];
let scrollPending = false;
function updateScroll() {
  const max = document.documentElement.scrollHeight - innerHeight;
  $('#progress').style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
  $('#nav').classList.toggle('scrolled', scrollY > 30);
  let current = chapters[0];
  for (const chapter of chapters) if (chapter.getBoundingClientRect().top < innerHeight * .55) current = chapter;
  $('#chapter-label').textContent = current.dataset.chapter;
  scrollPending = false;
}
addEventListener('scroll', () => {
  if (!scrollPending) { scrollPending = true; requestAnimationFrame(updateScroll); }
}, { passive: true });
addEventListener('resize', updateScroll);
updateScroll();

const carriers = [...document.querySelectorAll('[data-brand]')].map(button => button.dataset.brand);
let industry = 'telecom';
let selectedBrand = 'Metro by T-Mobile';
const form = $('#quoteForm');
function selectBrand(brand) {
  selectedBrand = brand;
  $('#activeBrandName').textContent = brand;
  form.elements.brand.value = brand;
  document.querySelectorAll('[data-brand]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.brand === brand)));
}
function setIndustry(next) {
  industry = next;
  document.querySelectorAll('[data-industry]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.industry === industry)));
  const brands = industry === 'telecom' ? carriers : ['Gas Station / Vape Shop'];
  $('#brandGrid').replaceChildren(...brands.map(brand => {
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'brand-choice'; button.dataset.brand = brand;
    button.append(document.createTextNode(brand));
    const arrow = document.createElement('span'); arrow.textContent = '↗'; arrow.setAttribute('aria-hidden', 'true');
    button.append(arrow); return button;
  }));
  const services = industry === 'telecom' ? telecomServices : retailServices;
  $('#servicesGrid').replaceChildren(...services.map((service, i) => {
    const article = document.createElement('article'); article.className = 'service-card';
    const number = document.createElement('span'); number.className = 'service-no'; number.textContent = String(i + 1).padStart(2, '0');
    const title = document.createElement('h3'); title.textContent = service.name;
    const description = document.createElement('p'); description.textContent = service.desc;
    const link = document.createElement('a'); link.href = '#contact'; link.dataset.service = service.name; link.textContent = 'Discuss this service ↗';
    article.append(number, title, description, link); return article;
  }));
  selectBrand(industry === 'telecom' ? 'Metro by T-Mobile' : 'Gas Station / Vape Shop');
}
document.querySelectorAll('[data-industry]').forEach(button => button.addEventListener('click', () => setIndustry(button.dataset.industry)));
$('#brandGrid').addEventListener('click', event => { const button = event.target.closest('[data-brand]'); if (button) selectBrand(button.dataset.brand); });
function addInterest(service) {
  const message = form.elements.message;
  if (!message.value.includes(service)) message.value = `${message.value.trim()}${message.value.trim() ? '\n' : ''}I'm interested in ${service}.`.slice(0, message.maxLength);
}
document.addEventListener('click', event => {
  const service = event.target.closest('[data-service]');
  if (service) { form.elements.brand.value = selectedBrand; addInterest(service.dataset.service); }
  const digital = event.target.closest('[data-digital]');
  if (digital) { form.elements.brand.value = digital.dataset.digital; addInterest(digital.dataset.digital); }
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const submit = form.querySelector('[type=submit]');
  if (submit.disabled) return;
  const label = submit.innerHTML;
  const notice = $('#formMsg');
  submit.disabled = true; submit.textContent = 'Sending your request…';
  notice.className = ''; notice.textContent = '';
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const payload = Object.fromEntries(new FormData(form));
    const response = await fetch('/api/quote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), signal: controller.signal });
    const result = await response.json();
    if (!response.ok || result.status !== 'success') throw new Error(result.message || 'Unable to send your request. Please try again.');
    notice.className = 'success'; notice.textContent = result.message || 'Thank you. An Archet strategist will reach out within one business day.';
    form.reset(); form.elements.brand.value = selectedBrand;
  } catch (error) {
    notice.className = 'error';
    notice.textContent = error.name === 'AbortError' ? 'The request timed out. Please try again or contact us directly.' : (error instanceof TypeError ? 'Please check your connection and try again.' : error.message);
  } finally { clearTimeout(timeout); submit.disabled = false; submit.innerHTML = label; }
});
