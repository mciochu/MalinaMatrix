(() => {
'use strict';
const apiRoot=()=>'http://'+location.hostname+':8088';
document.addEventListener('DOMContentLoaded',()=>{
 const el=id=>document.getElementById(id);
 const studio=el('message-studio');
 if(!studio)return;
 const txt=el('ms-text'),duration=el('ms-duration'),font=el('ms-font'),sendButton=el('ms-send'),stopButton=el('ms-stop');
 let selectedEffect='scroll_left',selectedFont='zegar_app/assets/fonts/8-series/MatrixChunky8X.bdf',busy=false;
 function status(message,type){
   const node=el('ms-status');
   node.textContent=message;
   node.className='ms-status'+(type?' '+type:'');
 }
 function updateCount(){el('ms-count').textContent=txt.value.length+' / 280';}
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
   if(!text){status('Wpisz najpierw wiadomość.','err');txt.focus();return;}
   setBusy(true);
   status('Wysyłam wiadomość…');
   try{
     const seconds=Number(duration.value);
     await call('/message',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({text,effect:selectedEffect,speed:35,duration:seconds,font:font.value})});
     status('Gotowe. Napis wyświetla się na matrycy.','ok');
   }catch(error){status('Nie udało się wysłać: '+error.message,'err');}
   finally{setBusy(false);}
 });
 stopButton.addEventListener('click',async()=>{
   if(busy)return;
   setBusy(true);
   status('Zatrzymuję napis…');
   try{
     await call('/message',{method:'POST',headers:{'Content-Type':'application/json'},
       body:JSON.stringify({stop:true})});
     status('Napis zatrzymany. Wrócił zegar.','ok');
   }catch(error){status('Nie udało się zatrzymać: '+error.message,'err');}
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
   status('Połączono z Maliną.','ok');
 }).catch(error=>status('Brak połączenia z Raspberry Pi: '+error.message,'err'));
});
})();
