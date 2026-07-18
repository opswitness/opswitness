const form = document.querySelector('#pair-form');
const nameInput = document.querySelector('#device-name');
const codeInput = document.querySelector('#pairing-code');
const errorBox = document.querySelector('#pair-error');
const submitButton = form.querySelector('button[type="submit"]');

const platformName = /iPhone/i.test(navigator.userAgent)
  ? 'iPhone'
  : /iPad/i.test(navigator.userAgent)
    ? 'iPad'
    : /Android/i.test(navigator.userAgent)
      ? 'Android device'
      : 'Browser';
nameInput.value = platformName;

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  submitButton.disabled = true;
  try {
    const response = await fetch('/api/v1/pairing/claim', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: codeInput.value, device_name: nameInput.value }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `Pairing failed (${response.status})`);
    }
    window.location.replace('/');
  } catch (error) {
    errorBox.textContent = error instanceof Error ? error.message : 'Pairing failed';
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});

if ('serviceWorker' in navigator && window.isSecureContext) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js'));
}
