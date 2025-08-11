const input = document.getElementById('inputText');
const output = document.getElementById('outputText');
const btn = document.getElementById('translateBtn');
const tone = document.getElementById('toneSelect');
const copyBtn = document.getElementById('copyBtn');

let sessionToken = null;

// Get session token when page loads
async function getSessionToken() {
  try {
    let url = 'http://localhost:5000/api/session';
    if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
      url = '/api/session';
    }
    
    const res = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      }
    });
    
    if (res.ok) {
      const data = await res.json();
      sessionToken = data.token;
    }
  } catch (err) {
    console.warn('Could not get session token:', err);
  }
}

// Initialize session token on page load
getSessionToken();

btn.addEventListener('click', async () => {
  const text = input.value.trim();
  if (!text) return alert('Please enter some text');
  
  // Get fresh token if we don't have one
  if (!sessionToken) {
    await getSessionToken();
  }
  
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
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Token': sessionToken
      },
      body: JSON.stringify({ 
        text, 
        tone: tone.value,
        session_token: sessionToken 
      })
    });
    
    const data = await res.json();
    if (!res.ok) {
      // If token expired, try getting a new one
      if (res.status === 401) {
        await getSessionToken();
        return btn.click(); // Retry with new token
      }
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
