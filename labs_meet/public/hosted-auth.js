'use strict';
// Included only by isolated SaaS HTTP entry point, never the static design preview.
(() => {
 const status=document.querySelector('#auth-status');
 const phone=document.querySelector('#phone');
 const send=document.querySelector('#otp-explain');
 const google=document.querySelector('#google-preview');
 let settings=null,challenge=null,attempting=false,gsiLoading=null;
 const field=document.createElement('div');field.hidden=true;
 const label=document.createElement('label');label.htmlFor='otp-code';label.textContent='4-digit sign-in code';
 const code=document.createElement('input');code.id='otp-code';code.inputMode='numeric';code.autocomplete='one-time-code';code.maxLength=4;code.pattern='[0-9]{4}';
 const verify=document.createElement('button');verify.className='button solid';verify.type='button';verify.textContent='Verify and open workspace';
 field.append(label,code,verify);send.after(field);
 const googleHost=document.createElement('div');googleHost.id='google-official-button';google.after(googleHost);
 document.querySelector('.preview-bar').textContent='EARLY ACCESS · Live meeting availability is shown inside your workspace.';
 document.querySelector('.closing>p').textContent='Sign in to your own workspace. Meeting actions stay subject to consent, review and current service availability.';
 document.querySelector('.auth-note').textContent='A 4-digit code expires in 3 minutes. Keep it private. WhatsApp delivery uses the Labs number; delivery is not guaranteed.';
 document.querySelector('.auth-method-note').textContent='Use your Google account. Google and WhatsApp create separate accounts unless you explicitly link them later.';
 async function api(path,data){
  const response=await fetch(path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:data===undefined?{}:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok)throw Error('Sign-in did not complete. Check your details and wait before trying again. An uncertain code send is not retried automatically.');
  return result;
 }
 async function begin(){settings=await api('/auth/begin');return settings;}
 function busy(value){attempting=value;send.disabled=value||Boolean(challenge);verify.disabled=value;google.disabled=value;}
 async function task(run){if(attempting)return;busy(true);status.textContent='Checking securely...';try{await run();}catch(e){status.textContent=e.message;}finally{busy(false);}}
 send.addEventListener('click',()=>task(async()=>{
  if(!/^\+[1-9][0-9]{7,14}$/.test(phone.value.trim())){status.textContent='Use your full WhatsApp number, including +country code.';return;}
  if(!settings)await begin();
  if(!settings.whatsapp_ready){status.textContent='WhatsApp sign-in is not available yet. No code was sent.';return;}
  const result=await api('/auth/otp/request',{phone:phone.value.trim()});challenge=result.challenge;field.hidden=false;phone.readOnly=true;send.disabled=true;
  status.textContent='Code request accepted. Check WhatsApp for your 4-digit code. It expires in 3 minutes. Do not resend if delivery is uncertain.';code.focus();
 }));
 verify.addEventListener('click',()=>task(async()=>{
  if(!challenge||!/^\d{4}$/.test(code.value)){status.textContent='Enter the 4-digit code from WhatsApp.';return;}
  await api('/auth/otp/verify',{challenge,code:code.value});code.value='';location.assign('/app/');
 }));
 google.addEventListener('click',()=>task(async()=>{
  if(!settings)await begin();
  if(!settings.google_client_id){status.textContent='Google sign-in is not available yet. No account was connected.';return;}
  if(!gsiLoading)gsiLoading=new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://accounts.google.com/gsi/client';script.async=true;script.onload=resolve;script.onerror=()=>reject(Error('Google sign-in could not load.'));document.head.append(script);});
  await gsiLoading;
  window.google.accounts.id.initialize({client_id:settings.google_client_id,nonce:settings.nonce,auto_select:false,use_fedcm_for_prompt:true,callback:async response=>{try{await api('/auth/google',{credential:response.credential});location.assign('/app/');}catch(e){status.textContent=e.message;}}});
  window.google.accounts.id.renderButton(googleHost,{type:'standard',theme:'outline',size:'large',text:'continue_with',width:Math.min(300,googleHost.clientWidth)});
  window.google.accounts.id.prompt();
  status.textContent='Choose your Google account. If One Tap is unavailable, use the Google button.';
 }));
})();
