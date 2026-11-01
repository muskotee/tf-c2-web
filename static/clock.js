'use strict';
(() => {
  let filled=false, dirty=false, busy=false, request=0, timer, pending=false, logoList='';
  const descriptions={digital:'Klassische Uhr mit Sekunden. Eingebaute Uhrschrift, optional mit Datum.',segment:'Digitale Ziffern und eine gerahmte Tafel – inspiriert von Börsen- und Anzeigetafeln.',binary:'BCD: Jede Dezimalziffer erhält eine Punktspalte. Von oben nach unten zählen die Zeilen 8, 4, 2 und 1. Gefüllte Punkte addieren; hohle Punkte sind aus.',arcade:'Pac-Man-Ziffern: Über jeder Ziffer frisst sich ein kleiner Held durch eine Punktleiste. Die Einer der Sekunden beginnen alle zehn Sekunden von vorn.',analog:'Analoge Uhr mit roten Stunden-, Minuten- und Sekundenzeigern. Daneben stehen die Uhrzeit und darunter das aktuelle Datum.',world:'Zwei Uhren nebeneinander. Die Städte und Zeitzonen wählst du selbst.'};
  function value(){return {style:$('clock-style').value,content:$('clock-content').value,color:$('clock-color').value,accent:$('clock-accent').value,timezone:$('clock-timezone').value,second_timezone:$('clock-second').value,date_format:$('clock-date-format').value,logo_id:$('clock-style').value==='world'?null:($('clock-logo').value||null),logo_position:$('clock-logo-position').value};}
  function controls(){
    const opt=value(),special=['analog','world'].includes(opt.style);
    $('clock-content').disabled=special;
    if(special)$('clock-content').value=opt.style==='analog'?'both':'time';
    $('clock-date-format').disabled=opt.style==='world'||$('clock-content').value==='time';
    $('clock-second-field').hidden=opt.style!=='world';
    $('clock-logo').disabled=opt.style==='world';
    $('clock-upload-button').disabled=opt.style==='world';
    $('clock-logo-position').disabled=opt.style==='world'||!$('clock-logo').value;
    $('clock-accent').disabled=!['segment','analog'].includes(opt.style);
    $('clock-description').textContent=descriptions[opt.style];
    document.querySelectorAll('[data-clock-style]').forEach(button=>{const selected=button.dataset.clockStyle===opt.style;button.classList.toggle('selected',selected);button.setAttribute('aria-pressed',String(selected));});
    $('clock-zones').textContent=$('clock-timezone').selectedOptions[0].textContent+(opt.style==='world'?' ↔ '+$('clock-second').selectedOptions[0].textContent:'');
    $('clock-tip-title').textContent=opt.style==='binary'?'Punkte lesen lernen.':opt.style==='arcade'?'Kleine Punkte. Große Jagd.':'Echte Uhr, kein Standbild.';
    $('clock-tip').textContent=opt.style==='binary'?'Beispiel 09: Die erste Spalte bleibt leer, die zweite hat 8 + 1. Je zwei Spalten bilden Stunden, Minuten und Sekunden.':opt.style==='arcade'?'Die Punktleisten gehören zu den einzelnen Ziffern. Sie bilden keinen umlaufenden 60-Sekunden-Rand. Die Sekunden werden von der echten Controlleruhr getaktet.':'Die Sekunden entstehen direkt auf dem Controller. Es wird nicht jede Sekunde ein neues Anzeigeprogramm geschrieben.';
  }
  async function preview(){
    if(pending)return;pending=true;const id=++request;
    try{const result=await api('/api/clock/preview',value());if(id!==request)return;$('clock-preview').src='data:image/png;base64,'+result.image;$('clock-error').hidden=true;}
    catch(error){$('clock-error').textContent=error.message;$('clock-error').hidden=false;}
    finally{pending=false;}
  }
  function changed(){dirty=true;controls();clearTimeout(timer);timer=setTimeout(preview,100);}
  $('clock-form').addEventListener('input',changed);$('clock-form').addEventListener('change',changed);
  document.querySelectorAll('[data-clock-style]').forEach(button=>button.addEventListener('click',()=>{$('clock-style').value=button.dataset.clockStyle;changed();}));
  $('clock-form').addEventListener('submit',async event=>{event.preventDefault();busy=true;try{await api('/api/clock/start',value());dirty=false;await poll();}catch(error){toast(error.message,true);}finally{busy=false;}});
  $('clock-stop').addEventListener('click',()=>job('/api/clock/stop'));
  $('clock-add-scene').addEventListener('click',async()=>{
    $('clock-add-scene').disabled=true;
    try{await window.MatrixStudio.addClock({...value(),duration:Number($('clock-scene-duration').value)});}catch(error){toast(error.message,true);}finally{$('clock-add-scene').disabled=false;}
  });
  $('clock-upload-button').addEventListener('click',()=>$('clock-upload').click());
  $('clock-upload').addEventListener('change',async()=>{
    const file=$('clock-upload').files[0];if(!file)return;
    if(file.size>2*1024*1024){toast('Das Bild darf höchstens 2 MB groß sein.',true);$('clock-upload').value='';return;}
    busy=true;$('clock-start').disabled=true;$('clock-upload-button').textContent='Bild wird geladen …';
    try{
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Datei konnte nicht gelesen werden.'));reader.readAsDataURL(file);});
      const logo=await api('/api/logo/upload',{name:file.name,data});
      await poll();$('clock-logo').value=logo.id;changed();toast('Logo gespeichert. Zum Anzeigen die Uhrgestaltung übernehmen.');
    }catch(error){toast(error.message,true);}finally{busy=false;$('clock-upload').value='';$('clock-upload-button').textContent='Logo hochladen';await poll();}
  });
  window.MatrixClock={applyOptions(opt){
    if(!filled&&state)window.MatrixClock.onState(state);
    if(opt.logo_id&&!Array.from($('clock-logo').options).some(o=>o.value===opt.logo_id)){
      const option=node('option','','Logo dieser Szene');option.value=opt.logo_id;$('clock-logo').append(option);
    }
    for(const [key,id] of Object.entries({style:'clock-style',content:'clock-content',color:'clock-color',accent:'clock-accent',timezone:'clock-timezone',second_timezone:'clock-second',date_format:'clock-date-format',logo_position:'clock-logo-position'}))if(opt[key]!==undefined)$(id).value=opt[key];
    $('clock-logo').value=opt.logo_id||'';$('clock-scene-duration').value=opt.duration||5;
    $('clock-logo-panel').open=Boolean(opt.logo_id);filled=true;changed();
  },onState(next){
    const stored=next.clock;if(!stored)return;
    const images=next.logos||[],key=JSON.stringify(images.map(im=>[im.id,im.name]));
    if(key!==logoList){
      const selected=filled?$('clock-logo').value:(stored.logo_id||'');logoList=key;
      const empty=node('option','','Kein Logo');empty.value='';$('clock-logo').replaceChildren(empty);
      for(const image of images){const option=node('option','',image.name);option.value=image.id;$('clock-logo').append(option);}
      $('clock-logo').value=selected;
    }
    const supported=next.clock_supported_styles||['digital','segment','analog','world'];
    const opt={...stored,style:supported.includes(stored.style)?stored.style:'digital'};
    for(const option of $('clock-style').options)option.disabled=!supported.includes(option.value);
    document.querySelectorAll('[data-clock-style]').forEach(button=>{button.disabled=!supported.includes(button.dataset.clockStyle);});
    if(!filled){for(const [key,id] of Object.entries({style:'clock-style',content:'clock-content',color:'clock-color',accent:'clock-accent',timezone:'clock-timezone',second_timezone:'clock-second',date_format:'clock-date-format',logo_position:'clock-logo-position'}))if(opt[key])$(id).value=opt[key];filled=true;if(opt.logo_id)$('clock-logo-panel').open=true;controls();}
    const running=['queued','running'].includes(next.job.state);
    $('clock-start').disabled=running||busy;
    $('clock-stop').disabled=running||!opt.enabled;
    $('clock-badge').textContent=opt.enabled?'AKTIV':next.timeline_clock?.enabled?'IN TIMELINE':'PAUSIERT';
    $('clock-start').textContent=opt.enabled?'Uhrgestaltung übernehmen ↗':'Uhr am Display starten ↗';
    $('clock-sync').textContent=opt.enabled?(opt.synced?'Letzter Zeitabgleich: '+date(opt.synced):'Zeitabgleich läuft …'):'Die Uhr ist nicht als aktuelle Anzeige aktiv.';
    if(next.last?.source==='clock'){$('last-title').textContent='Uhr & Datum';$('last-text').textContent=descriptions[next.last.clock?.style||'digital'];$('source-chip').textContent='UHR';}
  }};
  controls();setInterval(()=>{if(view==='clock')preview();},1000);
})();
