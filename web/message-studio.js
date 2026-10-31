(() => {
'use strict';
const apiRoot=()=>'http://'+location.hostname+':8088';
document.addEventListener('DOMContentLoaded',()=>{
 const el=id=>document.getElementById(id);
 const studio=el('message-studio');
 if(!studio)return;
 const txt=el('ms-text'),duration=el('ms-duration'),font=el('ms-font'),sendButton=el('ms-send'),stopButton=el('ms-stop');
 let selectedEffect='scroll_left',selectedFont='zegar_app/assets/fonts/8-series/MatrixChunky8X.bdf',busy=false;
 const tr=(key,params)=>window.MalinaI18n?.t(key,params)||key;
 let statusKey='message.connecting',statusParams={},statusType='';
 function status(key,params={},type=''){
   statusKey=key;statusParams=params&&typeof params==='object'?params:{};statusType=typeof params==='string'?params:type;
   const node=el('ms-status');
   node.textContent=tr(key,statusParams);
   node.className='ms-status'+(statusType?' '+statusType:'');
 }
 function updateCount(){el('ms-count').textContent=tr('message.count',{count:txt.value.length});}
 window.addEventListener('malina:languagechange',()=>{updateCount();status(statusKey,statusParams,statusType);});
 async function call(path,options){
   const response=await fetch(apiRoot()+path,Object.assign({cache:'no-store'},options||{}));
   if(!response.ok){
     let message='Błąd połączenia: HTTP '+response.status;
     try{message=(await response.json()).error||message;}catch(_){}
     throw new Error(message);
   }
   return response.json();
 }
 function setBusy(value){
   busy=value;
   sendButton.disabled=value;
   stopButton.disabled=value;
 }
 studio.querySelectorAll('[data-effect]').forEach(button=>{
   button.addEventListener('click',()=>{
     selectedEffect=button.dataset.effect;
     studio.querySelectorAll('[data-effect]').forEach(item=>{
       item.setAttribute('aria-pressed',String(item===button));
     });
   });
 });
 txt.addEventListener('input',updateCount);
 sendButton.addEventListener('click',async()=>{
   if(busy)return;
   const text=txt.value.trim();
   if(!text){status('message.empty',{},'err');txt.focus();return;}
   setBusy(true);
   status('message.sending');
   try{
     const seconds=Number(duration.value);
     await call('/message',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({text,effect:selectedEffect,speed:35,duration:seconds,font:font.value})});
     status('message.sent',{},'ok');
   }catch(error){status('message.sendError',{error:error.message},'err');}
   finally{setBusy(false);}
 });
 stopButton.addEventListener('click',async()=>{
   if(busy)return;
   setBusy(true);
   status('message.stopping');
   try{
     await call('/message',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({stop:true})});
     status('message.stopped',{},'ok');
   }catch(error){status('message.stopError',{error:error.message},'err');}
   finally{setBusy(false);}
 });
 updateCount();
 call('/message-options').then(options=>{
   const fonts=Array.isArray(options.fonts)?options.fonts:[];
   font.replaceChildren();
   fonts.forEach(item=>{
     const option=document.createElement('option');
     option.value=item.id;
     option.textContent=item.label.replace(/\\.bdf$/i,'');
     font.appendChild(option);
   });
   const preferred=fonts.find(item=>item.id.endsWith('/MatrixChunky8X.bdf'));
   selectedFont=preferred?preferred.id:(fonts[0]?fonts[0].id:'CONFIGURED');
   font.value=selectedFont;
   font.addEventListener('change',()=>{selectedFont=font.value;});
   status('message.connected',{},'ok');
 }) .catch(error=>status('message.noConnection',{error:error.message},'err'));
});
})();
