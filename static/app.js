'use strict';
const $ = (id) => document.getElementById(id);
let state = null, previews = [], pageIndex = 0, previewTimer, toastTimer, previewRequest = 0;
let lastLists = '', lastJob = '', autoFilled = false, view = 'text';
let autoDirty = false;
let measuredLayout = null, previewPending = true, previewValid = false;
let logoUploading = false;
let lastPreviewInput = null;
const copy = {
  text: ['TEXT & ANZEIGE', 'Eine Nachricht. In Licht.', 'Text gestalten, Vorschau prüfen und direkt an dein Display senden.'],
  studio: ['SZENENSTUDIO', 'Deine Szenen. Deine Reihenfolge.', 'Text, Logos und Effekte als Folge zusammenstellen, speichern und gemeinsam senden.'],
  rss: ['RSS-FEEDS', 'Die Welt auf deinem Display.', 'Deine Quellen. Deine Auswahl. Automatisch aktuelle Schlagzeilen.'],
  clock: ['UHR & DATUM', 'Zeit, die Spaß macht.', 'Digitale Ziffern, binäre Punkte und kleine Arcade-Momente für dein Display.'],
  presets: ['VORLAGEN', 'Gute Texte bleiben.', 'Gespeicherte Nachrichten laden, anpassen und wieder anzeigen.'],
  log: ['PROTOKOLL', 'Alles im Blick.', 'Bestätigte Übertragungen, RSS-Aktualisierungen und mögliche Fehler.'],
};
function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').classList.toggle('error', error);
  $('toast').hidden = false;
  toastTimer = setTimeout(() => $('toast').hidden = true, error ? 9000 : 4500);
}
async function api(path, value) {
  const response = await fetch(path, value === undefined ? {cache:'no-store'} : {
    method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(value),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Die Anfrage ist fehlgeschlagen.');
  return result;
}
function date(value) {
  return value ? new Date(value * 1000).toLocaleString('de-DE', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : 'Noch nicht aktualisiert';
}
function switchView(name) {
  if (!copy[name]) return;
  view = name;
  for (const key of Object.keys(copy)) $('view-' + key).hidden = key !== name;
  [$('page-kicker').textContent, $('page-title').textContent, $('page-subtitle').textContent] = copy[name];
  document.querySelectorAll('.nav-item').forEach(button => {
    button.classList.toggle('active', button.dataset.view === name);
    if (button.dataset.view === name) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  $('view-' + name).classList.remove('fade-in');
  requestAnimationFrame(() => $('view-' + name).classList.add('fade-in'));
}
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => switchView(button.dataset.view)));

function textOptions() {
  const logo = $('logo-select').value;
  return {text: logo && $('logo-position').value === 'alone' ? '' : $('message').value, mode: $('mode').value, size: Number($('size').value),
    align: $('align').value, color: document.querySelector('input[name=color]:checked').value,
    duration: Number($('duration').value), speed: Number($('speed').value), effect: $('effect').value,
    split_sizes:$('split-sizes').checked,size2:Number($('size2').value),
    background:$('background').value,frame:$('frame').value,frame_color:$('frame-color').value,frame_width:Number($('frame-width').value),
    logo_id:logo||null, logo_position:$('logo-position').value,
    logo_width:Number($('logo-width').value),logo_style:$('logo-style').value};
}
function applyOptions(opt) {
  for (const id of ['mode','size','align','duration','speed']) if (opt[id] !== undefined) {
    if(['duration','speed'].includes(id)&&!Array.from($(id).options).some(o=>o.value===String(opt[id]))){
      const option=node('option','',id==='duration'?`${opt[id]} Sekunden`:`${opt[id]} · eigener Wert`);option.value=String(opt[id]);$(id).append(option);
    }
    $(id).value = opt[id];
  }
  $('message').value = opt.text || '';
  $('background').value=opt.background||'black';
  $('frame').value=opt.frame||'none';
  $('frame-color').value=opt.frame_color||'amber';
  $('frame-width').value=opt.frame_width||1;
  $('frame-panel').open=Boolean(opt.frame&&opt.frame!=='none');
  $('split-sizes').checked=Boolean(opt.split_sizes);
  $('size2').value=opt.size2||12;
  $('logo-select').value = opt.logo_id || '';
  $('logo-position').value = opt.logo_position || 'left';
  $('logo-width').value = opt.logo_width || 32;
  $('logo-style').value = opt.logo_style || 'original';
  if(opt.logo_id)$('logo-panel').open=true;
  updateLogoControls();
  const color = document.querySelector('input[name=color][value="' + opt.color + '"]');
  if (color) color.checked = true;
  if (opt.effect && !Array.from($('effect').options).some(o => o.value === opt.effect)) {
    const item = node('option','',opt.effect); item.value = opt.effect; $('effect').append(item);
  }
  $('effect').value = opt.effect || (opt.mode === 'ticker' ? 'ticker_left' : 'direct');
  queuePreview();
}
function syncSendButton() {
  $('send-text').disabled = logoUploading || previewPending || !previewValid || ['queued','running'].includes(state?.job?.state);
  $('add-scene').disabled = logoUploading || previewPending || !previewValid;
}
function renderLogos(){
  const selected=$('logo-select').value;
  $('logo-select').replaceChildren();
  const empty=node('option','','Kein Logo');empty.value='';$('logo-select').append(empty);
  for(const logo of state?.logos||[]){const option=node('option','',logo.name);option.value=logo.id;$('logo-select').append(option);}
  $('logo-select').value=selected;
  updateLogoControls();
}
function updateLogoControls(){
  const id=$('logo-select').value;
  const selected=(state?.logos||[]).find(logo=>logo.id===id);
  const hasLogo=Boolean(id);
  $('logo-controls').hidden=!hasLogo;$('remove-logo').hidden=!hasLogo;$('logo-selected').hidden=!hasLogo;
  $('message').disabled=hasLogo&&$('logo-position').value==='alone';
  $('message').required=!hasLogo;
  if(selected){$('logo-thumb').src=selected.url;$('logo-info').textContent=`${selected.name} · ${selected.width} × ${selected.height} Pixel`;}else{$('logo-thumb').removeAttribute('src');}
  const max=$('logo-position').value==='alone'||!$('message').value.trim()?128:64;
  for(const option of $('logo-width').options){option.disabled=Number(option.value)>max;option.hidden=option.disabled;}
  if(Number($('logo-width').value)>max)$('logo-width').value='32';
}
$('remove-logo').addEventListener('click',()=>{$('logo-select').value='';updateLogoControls();queuePreview();});
$('logo-upload-label').addEventListener('click',()=>$('logo-upload').click());
$('logo-position').addEventListener('change',()=>{
  if($('logo-position').value==='alone')$('logo-width').value='128';
  updateLogoControls();queuePreview();
});
$('logo-upload').addEventListener('change',async()=>{
  const file=$('logo-upload').files[0];if(!file)return;
  if(file.size>2*1024*1024){toast('Das Bild darf höchstens 2 MB groß sein.',true);$('logo-upload').value='';return;}
  logoUploading=true;$('logo-upload-label').textContent='Bild wird geladen …';syncSendButton();
  try{
    const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('Datei konnte nicht gelesen werden.'));reader.readAsDataURL(file);});
    const logo=await api('/api/logo/upload',{name:file.name,data});
    await poll();$('logo-select').value=logo.id;$('logo-panel').open=true;updateLogoControls();queuePreview();toast('Logo gespeichert. Die Vorschau wird aktualisiert.');
  }catch(error){toast(error.message,true);}finally{logoUploading=false;$('logo-upload-label').textContent='Bild hochladen';$('logo-upload').value='';syncSendButton();}
});
function setEffects(id, items, selected) {
  const select = $(id);
  const signature = JSON.stringify(items);
  if (select.dataset.items !== signature) {
    select.replaceChildren();
    for (const item of items) {const option = node('option','',item.label);option.value=item.value;select.append(option);}
    select.dataset.items = signature;
  }
  select.value = items.some(e => e.value === selected) ? selected : (items[0]?.value || '');
}
function showLayout(result) {
  measuredLayout = result.layout;
  const layout = measuredLayout, fit = layout.current;
  $('mode').value = result.options.mode;
  $('size').value = result.options.size;
  $('size2').value = result.options.size2;
  $('split-sizes').checked=Boolean(result.options.split_sizes);
  $('size2-field').hidden=!result.options.split_sizes;
  document.querySelector('label[for="size"]').textContent=result.options.split_sizes?'Erste Textzeile':'Schriftgröße';
  for (const option of $('mode').options) {
    option.disabled = !layout.allowed_modes.includes(option.value);
    option.hidden = option.disabled;
  }
  for (const option of $('size').options) {
    const profile = layout.sizes.find(p => p.size === Number(option.value));
    const allowed = result.options.mode === 'static' ? profile.fits
      : result.options.mode === 'ticker' ? profile.ticker_allowed
      : result.options.mode === 'pages' ? profile.pages_allowed : profile.pages_allowed || profile.ticker_allowed;
    option.disabled = !allowed;
    option.textContent = `${profile.size} px · ${profile.fits ? 'passt auf 1 Seite' : profile.pages + ' Textseiten'}`;
  }
  for(const option of $('size2').options){
    const profile=layout.sizes2.find(p=>p.size2===Number(option.value));
    if(!profile){option.disabled=false;option.textContent=`${option.value} px`;continue;}
    option.disabled=result.options.mode==='static'?!profile.fits:!profile.pages_allowed;
    option.textContent=`${profile.size2} px · ${profile.fits?'passt zusammen':profile.pages+' Textseiten'}`;
  }
  setEffects('effect',layout.effects,result.options.effect);
  const modeNames = {static:'Standbild',pages:'Textseiten',ticker:'Laufschrift'};
  const intro = fit.fits ? `Passt vollständig: ${fit.lines} von ${fit.rows} möglichen Zeilen auf 128 × 32 Pixel.`
    : `Bei ${fit.size} px: ${fit.lines} umgebrochene Zeilen, ${fit.pages} Textseiten. Ein Standbild würde nicht vollständig passen.`;
  $('fit-message').textContent = ((result.adjustments||[]).join(' ') + ' ').trimStart() + intro
    + (result.options.mode === 'auto' ? ` Automatik wählt ${modeNames[layout.effective_mode]}.` : '');
  $('fit-message').classList.toggle('multi-page',!fit.fits);
  if(layout.split_sizes&&!layout.logo_only){
    $('fit-message').textContent=`Erste Textzeile ${result.options.size} px, zweite ${result.options.size2} px · `
      +(fit.fits?`${fit.height} von 32 Pixel Höhe: passt vollständig.`:`${fit.height} Pixel Gesamthöhe nach Umbruch: ${fit.pages} Textseiten nötig.`)
      +(result.options.mode==='auto'?` Automatik wählt ${modeNames[layout.effective_mode]}.`:'');
  }
  $('duration-field').hidden = layout.effective_mode === 'ticker';
  $('speed-field').hidden = result.options.effect === 'direct';
  $('align').disabled = layout.effective_mode === 'ticker';
  $('size').disabled=layout.logo_only;
  $('size2').disabled=layout.logo_only;
  $('split-sizes').disabled=layout.logo_only;
  $('align').disabled=layout.logo_only||layout.effective_mode==='ticker';
  document.querySelector('.color-field').disabled=layout.logo_only&&$('logo-style').value!=='solid';
  $('frame-color').disabled=$('frame').value==='none';
  $('frame-width').disabled=$('frame').value==='none';
  const sameColor=result.options.color===result.options.background;
  $('contrast-hint').textContent=sameColor?'Text und Hintergrund haben dieselbe Farbe; der Text ist dadurch unsichtbar.':'Für gut lesbaren Text unterschiedliche Text- und Hintergrundfarben wählen.';
  if(layout.logo){
    $('fit-message').textContent=layout.logo_only
      ? `Logo ${layout.logo.width} × ${layout.logo.height} Pixel · vollständig und zentriert auf 128 × 32 Pixel.`
      : `${layout.logo.width} × ${layout.logo.height} Pixel Logo · ${layout.text_width} Pixel für Text. `+(fit.fits?'Text passt vollständig auf eine Seite.':`${fit.pages} Textseiten nötig; Umbruch wird automatisch angepasst.`);
    $('fit-message').classList.toggle('multi-page',!layout.logo_only&&!fit.fits);
  }
  if(layout.inset)$('fit-message').textContent+=` Rahmen berücksichtigt: ${layout.text_width} × ${layout.content_height} Pixel für Text. Eine Laufschrift ist mit Rahmen nicht verfügbar.`;
}
function paintPreview() {
  $('preview-image').removeAttribute('src');
  if (previews.length) $('preview-image').src = 'data:image/png;base64,' + previews[pageIndex];
  $('preview-position').textContent = previews.length ? `Seite ${pageIndex + 1} von ${previews.length}` : 'Keine Vorschau';
  $('prev-page').disabled = previews.length < 2;
  $('next-page').disabled = previews.length < 2;
}
async function preview() {
  const request = ++previewRequest;
  if (!$('message').value.trim()&&!$('logo-select').value) {
    previews = []; pageIndex = 0; paintPreview(); $('preview-error').hidden = true;
    previewPending=false;previewValid=false;syncSendButton();$('fit-message').textContent='Bitte einen Text eingeben.';return;
  }
  try {
    const result = await api('/api/preview', textOptions());
    if (request !== previewRequest) return;
    previews = result.pages; pageIndex = 0; paintPreview();
    showLayout(result);
    previewPending=false;previewValid=true;syncSendButton();
    $('preview-error').hidden = true;
    const label = result.layout.effects.find(e=>e.value===result.options.effect)?.label || '';
    $('preview-note').textContent = result.layout.effective_mode === 'ticker'
      ? `${previews.length} Bildstreifen · ${label}. Die Vorschau zeigt die einzelnen Streifen; die Bewegung läuft auf dem Display.`
      : `${previews.length} Seite(n) · ${$('duration').value} Sekunden pro Seite · ${label}. Die Vorschau zeigt das fertige Bild; der Effekt läuft auf dem Display.`;
  } catch (error) {
    if (request !== previewRequest) return;
    $('preview-error').textContent = error.message; $('preview-error').hidden = false;
    previewPending=false;previewValid=false;syncSendButton();
  }
}
function queuePreview() {
  updateLogoControls();
  $('size2-field').hidden=!$('split-sizes').checked;
  document.querySelector('label[for="size"]').textContent=$('split-sizes').checked?'Erste Textzeile':'Schriftgröße';
  $('char-count').textContent = `${$('message').value.length} / 2000`;
  const signature=JSON.stringify(textOptions());
  // A textarea also emits change on blur. Do not disable Send again for an
  // unchanged value when the click that blurs it is already submitting.
  if(signature===lastPreviewInput&&(previewValid||previewPending))return;
  lastPreviewInput=signature;
  previewRequest++;
  previewPending=true;previewValid=false;syncSendButton();
  $('fit-message').textContent='Text und verfügbare Optionen werden vermessen …';
  $('duration-field').hidden = $('mode').value === 'ticker';
  $('speed-field').hidden = $('effect').value === 'direct';
  clearTimeout(previewTimer); previewTimer = setTimeout(preview, 300);
}
$('text-form').addEventListener('input', queuePreview);
$('text-form').addEventListener('change', queuePreview);
$('prev-page').addEventListener('click', () => { if (previews.length) {pageIndex = (pageIndex + previews.length - 1) % previews.length; paintPreview();} });
$('next-page').addEventListener('click', () => { if (previews.length) {pageIndex = (pageIndex + 1) % previews.length; paintPreview();} });

async function job(path, value = {}) {
  try { await api(path, value); await poll(); }
  catch (error) { toast(error.message, true); }
}
let brightnessEditing=false;
$('brightness').addEventListener('input',()=>{
  brightnessEditing=true;
  $('brightness-value').textContent=`Stufe ${Number($('brightness').value)+1} / 16`;
  $('brightness-status').textContent='Zum Übernehmen loslassen';
});
$('brightness').addEventListener('change',async()=>{
  const level=Number($('brightness').value);
  $('brightness').disabled=true;
  try{await api('/api/brightness',{level});}
  catch(error){toast(error.message,true);}
  finally{brightnessEditing=false;await poll();}
});
$('text-form').addEventListener('submit', async (event) => {event.preventDefault(); await job('/api/send', textOptions());});
$('probe').addEventListener('click', () => job('/api/probe'));
$('send-rss').addEventListener('click', () => job('/api/rss/send'));
$('refresh-rss').addEventListener('click', () => job('/api/rss/refresh'));

function fillAuto(force = false) {
  if (!state || (autoFilled && !force)) return;
  const auto = state.auto;
  for (const [field,key] of [['rss-interval','interval'],['rss-headlines','headlines'],['rss-mode','mode'],['rss-size','size']]) {
    if (!Array.from($(field).options).some(opt => opt.value === String(auto[key]))) {
      const opt = node('option', '', `${auto[key]}`); opt.value = auto[key]; $(field).append(opt);
    }
    $(field).value = auto[key];
  }
  $('rss-enabled').checked = auto.enabled;
  fillRssEffects(auto.effect);
  autoFilled = true;
}
function fillRssEffects(selected) {
  if (!state?.effects) return;
  const ticker = $('rss-mode').value === 'ticker';
  setEffects('rss-effect',state.effects.filter(e=>e.ticker===ticker),selected||$('rss-effect').value);
}
$('rss-mode').addEventListener('change',()=>fillRssEffects());
$('auto-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await api('/api/rss/settings', {enabled:$('rss-enabled').checked,
      interval:Number($('rss-interval').value), headlines:Number($('rss-headlines').value),
      mode:$('rss-mode').value, size:Number($('rss-size').value),effect:$('rss-effect').value});
    autoDirty = false; await poll(); fillAuto(true); toast('RSS-Automatik gespeichert.');
  } catch (error) { toast(error.message, true); }
});
$('auto-form').addEventListener('input', () => autoDirty = true);

function empty(icon, title, message) {
  const el = node('div','empty-state'); el.append(node('div','empty-icon',icon),node('h3','',title),node('p','',message)); return el;
}
function button(label, action, className='text-link') {
  const el = node('button',className,label); el.type = 'button'; el.addEventListener('click', action); return el;
}
function renderFeeds() {
  const list = $('feed-list'); list.replaceChildren();
  if (!state.feeds.length) list.append(empty('◔','Noch keine Quellen hinterlegt','Trage unten deine erste Feed-Adresse ein. Du kannst sie vor dem Speichern prüfen.'));
  for (const source of state.feeds) {
    const row = node('article','feed-row');
    const top = node('div','feed-top'); top.append(node('h3','feed-title',source.name),node('span','chip',source.enabled?'AKTIV':'PAUSIERT'));
    row.append(top,node('p','feed-url',source.url));
    if (source.error) row.append(node('p','feed-error',source.error));
    if (source.items.length) {
      const items = node('ol','feed-items'); source.items.slice(0,3).forEach(item => items.append(node('li','',item.title))); row.append(items);
    }
    const actions = node('div','feed-actions');
    actions.append(button('Bearbeiten',()=>editFeed(source)),button(source.enabled?'Pausieren':'Aktivieren',async()=>{
      try {await api('/api/feed/save',{...source,enabled:!source.enabled});await poll();}catch(e){toast(e.message,true);}
    }),button('Entfernen',async()=>{
      if (!confirm(`Quelle „${source.name}“ entfernen?`)) return;
      try {await api('/api/feed/delete',{id:source.id});await poll();}catch(e){toast(e.message,true);}
    }),node('span','feed-status',date(source.updated)));
    row.append(actions); list.append(row);
  }
  $('feed-count').textContent = state.feeds.length;
  $('sources-label').textContent = `${state.feeds.length} FEED${state.feeds.length===1?'':'S'}`;
}
function editFeed(source) {
  $('feed-id').value = source.id; $('feed-name').value = source.name; $('feed-url').value = source.url;
  $('feed-form-title').textContent = 'Quelle bearbeiten'; $('cancel-feed').hidden = false;
  $('feed-check').hidden = true; $('feed-name').focus();
}
function resetFeed() {
  $('feed-form').reset(); $('feed-id').value = ''; $('feed-form-title').textContent = 'Feed hinzufügen';
  $('cancel-feed').hidden = true; $('feed-check').hidden = true;
}
$('cancel-feed').addEventListener('click', resetFeed);
$('feed-form').addEventListener('submit', async event => {
  event.preventDefault(); const old = state?.feeds.find(feed => feed.id === $('feed-id').value);
  $('store-feed').disabled = true;
  try {
    await api('/api/feed/save',{id:$('feed-id').value||undefined,name:$('feed-name').value,url:$('feed-url').value,enabled:old?old.enabled:true});
    resetFeed(); await poll(); toast('Quelle gespeichert.');
  } catch(error) {toast(error.message,true);} finally {$('store-feed').disabled=false;}
});
$('check-feed').addEventListener('click', async()=>{
  if (!$('feed-url').reportValidity()) return;
  $('check-feed').disabled=true; $('check-feed').textContent='Wird geprüft …';
  try {
    const result = await api('/api/feed/check',{url:$('feed-url').value});
    if (!$('feed-name').value.trim()) $('feed-name').value=result.title;
    const list=node('ol');result.items.slice(0,5).forEach(item=>list.append(node('li','',item.title)));
    $('feed-check').replaceChildren(node('h3','',`✓ ${result.title} · ${result.items.length} Meldungen`),list);
    $('feed-check').hidden=false;
  } catch(error){toast(error.message,true);} finally{$('check-feed').disabled=false;$('check-feed').textContent='Feed prüfen';}
});

$('save-preset').addEventListener('click',()=>{
  if (!$('message').value.trim()&&!$('logo-select').value) return toast('Bitte einen Text eingeben oder ein Logo auswählen.',true);
  $('preset-name').value='';$('preset-dialog').showModal();$('preset-name').focus();
});
$('close-preset').addEventListener('click',()=>$('preset-dialog').close());
$('preset-form').addEventListener('submit', async event=>{
  event.preventDefault();
  try {await api('/api/preset/save',{...textOptions(),name:$('preset-name').value});$('preset-dialog').close();await poll();toast('Vorlage gespeichert.');}
  catch(error){toast(error.message,true);}
});
function renderPresets() {
  const list=$('preset-list');list.replaceChildren();
  if(!state.presets.length)list.append(empty('▤','Platz für deine Lieblingstexte','Schreibe eine Nachricht und wähle „Als Vorlage speichern“. Gestaltung und Text werden gemeinsam gesichert.'));
  for(const preset of state.presets){
    const modeLabel={ticker:'LAUFSCHRIFT',pages:'TEXTSEITEN',auto:'AUTOMATIK',static:'STANDBILD'}[preset.options.mode]||'TEXTSEITEN';
    const logo=(state.logos||[]).find(image=>image.id===preset.options.logo_id);
    const fontLabel=preset.options.split_sizes?`${preset.options.size} / ${preset.options.size2} PX`:`${preset.options.size} PX`;
    const card=node('article','card preset-card');card.append(node('span','eyebrow',`${fontLabel} / ${modeLabel}`),node('h3','',preset.name),node('p','',preset.options.text||(logo?'Logo: '+logo.name:'')));
    if(logo){const thumb=node('img','preset-logo');thumb.src=logo.url;thumb.alt=logo.name;card.append(thumb);}
    const actions=node('div','form-actions');actions.append(button('Laden & bearbeiten',()=>{applyOptions(preset.options);switchView('text');toast('Vorlage geladen.');},'button secondary'),button('Entfernen',async()=>{
      if(!confirm(`Vorlage „${preset.name}“ entfernen?`))return;
      try{await api('/api/preset/delete',{id:preset.id});await poll();}catch(error){toast(error.message,true);}
    }));card.append(actions);list.append(card);
  }
}
function renderEvents(){
  const list=$('event-list');list.replaceChildren();
  if(!state.events.length)list.append(empty('≡','Hier entsteht dein Protokoll','Übertragungen und Fehler erscheinen nach der ersten Aktion automatisch.'));
  for(const entry of state.events){const row=node('article','event '+entry.kind),body=node('div');body.append(node('p','',entry.message),node('time','',date(entry.created)));row.append(node('span','event-marker'),body);list.append(row);}
}
async function poll(){
  try{
    state=await api('/api/state');
    const device=state.device, busy=['queued','running'].includes(state.job.state);
    if(!brightnessEditing){
      $('brightness').disabled=busy||!device.connected||!Number.isInteger(device.brightness);
      if(Number.isInteger(device.brightness)){
        $('brightness').value=device.brightness;
        $('brightness-value').textContent=`Stufe ${device.brightness+1} / 16`;
        $('brightness-status').textContent=device.brightness_manual?'Manuell · vom Display gelesen':'Zeitplan aktiv · Regler setzt manuelle Helligkeit';
      }
    }
    const conn=$('connection');conn.replaceChildren(node('span','status-dot '+(device.connected?'online':device.checking?'':'offline')),node('span','',device.connected?'Display verbunden':device.checking?'Verbindung prüfen …':'Display nicht erreichbar'));
    conn.title=device.error||device.firmware;
    $('side-dot').className='status-dot '+(device.connected?'online':'offline');
    for(const id of ['send-rss','refresh-rss','probe'])$(id).disabled=busy;
    syncSendButton();
    const job=state.job;
    $('job-strip').hidden=job.state==='idle';$('job-strip').classList.toggle('error',job.state==='error');
    $('job-label').textContent=job.state==='error'?'Aktion fehlgeschlagen':job.state==='done'?'Fertig':'Einen Moment …';
    $('job-percent').textContent=busy?`${job.progress}%`:'';
    $('job-progress').style.width=`${job.progress}%`;$('job-message').textContent=job.message;
    if(job.id && job.id+job.state!==lastJob){lastJob=job.id+job.state;if(job.state==='done')toast(job.message);if(job.state==='error')toast(job.message,true);}
    const listKey=JSON.stringify([state.feeds,state.presets,state.events,state.logos]);
    if(listKey!==lastLists){lastLists=listKey;renderFeeds();renderPresets();renderEvents();renderLogos();}
    fillAuto(!autoDirty);
    $('auto-badge').textContent=state.auto.enabled?'AKTIV':'PAUSIERT';
    $('next-refresh').textContent=state.auto.enabled?`Nächste Aktualisierung: ${date(state.auto.next)}`:'Automatik ist pausiert.';
    if(state.last){
      const lastLogo=(state.logos||[]).find(image=>image.id===state.last.options.logo_id);
      $('last-title').textContent=state.last.source==='rss'?'Aktuelle RSS-Schlagzeilen':lastLogo?(state.last.options.text?'Logo & Text':'Dein Logo'):'Deine letzte Nachricht';
      $('last-text').textContent=state.last.options.text.slice(0,150)+(state.last.options.text.length>150?' …':'')+(!state.last.options.text&&lastLogo?lastLogo.name:'');
      $('last-time').textContent=`${date(state.last.sent)} · ${state.last.pages} Seite(n)`;
      $('source-chip').textContent=state.last.source==='rss'?'RSS':'MANUELL';
      if(state.last.source==='timeline'){
        $('last-title').textContent=state.last.name||'Deine Timeline';
        $('last-text').textContent=`${state.last.scene_count} Szenen · ${state.last.pages} Seiten · `+(state.last.scenes||[]).map(s=>s.name).join(' → ');
        $('source-chip').textContent='TIMELINE';
      }
    }
    window.MatrixStudio?.onState(state);
    window.MatrixClock?.onState(state);
  }catch(error){
    $('connection').replaceChildren(node('span','status-dot offline'),node('span','','Websteuerung nicht erreichbar'));
    $('side-dot').className='status-dot offline';
  }
}
queuePreview();poll();setInterval(poll,2500);
