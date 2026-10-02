'use strict';
document.querySelector('#login-form')?.addEventListener('submit',event=>{
  const button=event.target.querySelector('button[type=submit]');
  button.disabled=true;button.textContent='Entrando…';
});
