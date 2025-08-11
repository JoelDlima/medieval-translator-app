const input = document.getElementById('inputText');
const output = document.getElementById('outputText');
const btn = document.getElementById('translateBtn');
const tone = document.getElementById('toneSelect');
const copyBtn = document.getElementById('copyBtn');

btn.addEventListener('click', async () => {
  const text = input.value.trim();
  if (!text) return alert('Please enter some text');
  btn.disabled = true;
  btn.innerText = 'Translating...';
  try {
    // Use API endpoints (works both locally and deployed)
    let url = 'http://localhost:5000/api/translate';
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      url = '/api/translate';
    }
    
    const res = await fetch(url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ text, tone: tone.value })
    });
    const data = await res.json();
    if (!res.ok) {
      output.value = data.error || JSON.stringify(data);
    } else {
      output.value = data.result || '';
    }
  } catch (err) {
    output.value = 'Error connecting to backend: ' + err.message;
  } finally {
    btn.disabled = false;
    btn.innerText = 'Translate';
  }
});

copyBtn.addEventListener('click', async () => {
  const text = output.value;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    const original = copyBtn.innerText;
    copyBtn.innerText = 'Copied!';
    copyBtn.classList.add('success');
    setTimeout(() => {
      copyBtn.innerText = original;
      copyBtn.classList.remove('success');
    }, 1000);
  } catch (e) {
    alert('Could not copy to clipboard');
  }
});
