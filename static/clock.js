'use strict';
(() => {
  let filled=false, dirty=false, busy=false, request=0, timer, pending=false;
  const descriptions={digital:'Klassische Uhr mit Sekunden. Eingebaute Uhrschrift, optional mit Datum.',segment:'Digitale Ziffern und eine gerahmte Tafel – inspiriert von Börsen- und Anzeigetafeln.',binary:'BCD: Jede Dezimalziffer erhält eine Punktspalte. Von oben nach unten zählen die Zeilen 8, 4, 2 und 1. Gefüllte Punkte addieren; hohle Punkte sind aus.',arcade:'Pac-Man-Ziffern: Über jeder Ziffer frisst sich ein kleiner Held durch eine Punktleiste. Die Einer der Sekunden beginnen alle zehn Sekunden von vorn.',analog:'Eine analoge Uhr mit Stunden-, Minuten- und Sekundenzeiger, daneben die digitale Uhrzeit.',world:'Zwei Uhren nebeneinander. Die Städte und Zeitzonen wählst du selbst.'};
  function value(){return {style:$('clock-style').value,content:$('clock-content').value,color:$('clock-color').value,accent:$('clock-accent').value,timezone:$('clock-timezone').value,second_timezone:$('clock-second').value,date_format:$('clock-date-format').value};}
  function controls(){
    const opt=value(),special=['analog','world'].includes(opt.style);
    $('clock-content').disabled=special;
    $('clock-date-format').disabled=special||$('clock-content').value==='time';
    if(special)$('clock-content').value='time';
    $('clock-second-field').hidden=opt.style!=='world';
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
  window.MatrixClock={onState(next){
    const stored=next.clock;if(!stored)return;
    const supported=next.clock_supported_styles||['digital','segment','analog','world'];
    const opt={...stored,style:supported.includes(stored.style)?stored.style:'digital'};
    for(const option of $('clock-style').options)option.disabled=!supported.includes(option.value);
    document.querySelectorAll('[data-clock-style]').forEach(button=>{button.disabled=!supported.includes(button.dataset.clockStyle);});
    if(!filled){for(const [key,id] of Object.entries({style:'clock-style',content:'clock-content',color:'clock-color',accent:'clock-accent',timezone:'clock-timezone',second_timezone:'clock-second',date_format:'clock-date-format'}))if(opt[key])$(id).value=opt[key];filled=true;controls();}
    const running=['queued','running'].includes(next.job.state);
    $('clock-start').disabled=running||busy;
    $('clock-stop').disabled=running||!opt.enabled;
    $('clock-badge').textContent=opt.enabled?'AKTIV':'PAUSIERT';
    $('clock-start').textContent=opt.enabled?'Uhrgestaltung übernehmen ↗':'Uhr am Display starten ↗';
    $('clock-sync').textContent=opt.enabled?(opt.synced?'Letzter Zeitabgleich: '+date(opt.synced):'Zeitabgleich läuft …'):'Die Uhr ist nicht als aktuelle Anzeige aktiv.';
    if(next.last?.source==='clock'){$('last-title').textContent='Uhr & Datum';$('last-text').textContent=descriptions[next.last.clock?.style||'digital'];$('source-chip').textContent='UHR';}
  }};
  controls();setInterval(()=>{if(view==='clock')preview();},1000);
})();
