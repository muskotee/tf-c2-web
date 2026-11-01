'use strict';
(() => {
  const STORAGE = 'matrix.timeline.v1';
  const clone = value => JSON.parse(JSON.stringify(value));
  const uid = () => 's-' + Array.from(crypto.getRandomValues(new Uint8Array(8)), n => n.toString(16).padStart(2,'0')).join('');
  let project = {id:null,name:'Meine Timeline',scenes:[]}, selected = null, editing = null;
  let zoom = 36, version = 0, request = 0, dirty = false, ready = false, refreshTimer;
  let serverState = null, projectListKey = '', time = 0, playing = false, frame, lastTick = 0, monitorKey = '';
  const cache = new Map(), undo = [], redo = [];
  try {
    const draft = JSON.parse(localStorage.getItem(STORAGE));
    if (draft && Array.isArray(draft.project?.scenes) && draft.project.scenes.length <= 30) {
      project = draft.project; selected = draft.selected || project.scenes[0]?.id || null;
      zoom = Math.max(24, Math.min(72, Number(draft.zoom)||36)); dirty = true;
    }
  } catch (_) { /* An invalid draft never replaces saved Raspberry projects. */ }

  const snapshot = () => clone({project, selected});
  const payload = () => clone(project);
  const scene = () => project.scenes.find(s => s.id === selected);
  const info = s => cache.get(s.id);
  const seconds = s => info(s)?.preview_seconds || Number(s.options.duration)||5;
  const total = () => project.scenes.reduce((n,s) => n + seconds(s),0);
  const startOf = id => {let n=0;for(const s of project.scenes){if(s.id===id)break;n+=seconds(s);}return n;};
  const stamp = n => {n=Math.max(0,Math.floor(n));return `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;};
  function persist() {
    try {
      localStorage.setItem(STORAGE,JSON.stringify({project,selected,zoom}));
      $('studio-draft-status').textContent = dirty ? 'Entwurf im Browser gesichert · zum dauerhaften Speichern „Projekt speichern“ wählen.' : 'Projekt auf dem Raspberry gespeichert.';
    } catch (_) { $('studio-draft-status').textContent='Browserspeicher nicht verfügbar. Bitte das Projekt auf dem Raspberry speichern.'; }
  }
  function pause() {
    playing=false;cancelAnimationFrame(frame);$('studio-play').textContent='▶ Vorschau starten';
  }
  function cancelEdit() {
    editing=null;$('scene-edit-banner').hidden=true;$('add-scene').textContent='Als Szene zur Timeline hinzufügen ＋';
    $('clock-scene-edit-banner').hidden=true;$('clock-add-scene').textContent='Als Uhrszene zur Timeline hinzufügen ＋';
  }
  function commit(change) {
    undo.push(snapshot());if(undo.length>30)undo.shift();redo.length=0;
    pause();change();version++;dirty=true;ready=false;
    if(editing&&!project.scenes.some(s=>s.id===editing))cancelEdit();
    if(!project.scenes.some(s=>s.id===selected))selected=project.scenes[0]?.id||null;
    time=Math.min(time,total());persist();render();schedulePreview();
  }
  function restore(stack, other) {
    if(!stack.length)return;other.push(snapshot());const value=stack.pop();
    pause();project=value.project;selected=value.selected;version++;dirty=true;ready=false;cancelEdit();persist();render();schedulePreview();
  }
  function schedulePreview() {
    clearTimeout(refreshTimer);request++;
    if(!project.scenes.length){ready=false;$('studio-error').hidden=true;render();return;}
    refreshTimer=setTimeout(refresh,250);
  }
  async function refresh() {
    const current=++request, revision=version;
    try {
      const result=await api('/api/timeline/preview',payload());
      if(current!==request||revision!==version)return;
      for(const value of result.scenes)cache.set(value.id,value);
      project.scenes=project.scenes.map(s=>({...s,options:cache.get(s.id).options}));
      ready=true;$('studio-error').hidden=true;persist();render();
    } catch(error) {
      if(current!==request||revision!==version)return;
      ready=false;$('studio-error').textContent=error.message;$('studio-error').hidden=false;render();
    }
  }
  function segments() {
    let cursor=0;const result=[];
    for(const s of project.scenes){
      const pages=info(s)?.pages||[null],duration=Number(s.options.duration)||5;
      pages.forEach((image,index)=>{result.push({scene:s,image,index,start:cursor,end:cursor+duration});cursor+=duration;});
    }
    return result;
  }
  function monitor() {
    const length=total();time=Math.max(0,Math.min(time,length));
    const all=segments(),part=all.find(p=>time<p.end)||all[all.length-1];
    const key=part?`${part.scene.id}:${part.index}:${part.image||''}`:'';
    if(key!==monitorKey){
      monitorKey=key;
      if(part?.image)$('studio-monitor-image').src='data:image/png;base64,'+part.image;
      else $('studio-monitor-image').removeAttribute('src');
    }
    $('studio-monitor-title').textContent=part?`${part.scene.name} · Seite ${part.index+1}`:'NOCH KEINE SZENEN';
    $('studio-time').textContent=`${stamp(time)} / ${stamp(length)}`;
    $('studio-seek').max=String(length||1);$('studio-seek').value=String(time);
    $('studio-playhead').style.left=`${time*zoom}px`;
    for(const card of $('studio-track').children){
      card.classList.toggle('selected',card.dataset.id===selected);
      card.classList.toggle('playing',playing&&card.dataset.id===part?.scene.id);
    }
    if(playing){const position=time*zoom,scroll=$('studio-scroll');if(position<scroll.scrollLeft||position>scroll.scrollLeft+scroll.clientWidth-50)scroll.scrollLeft=Math.max(0,position-scroll.clientWidth/3);}
  }
  function seek(value, select=false) {
    time=Math.max(0,Math.min(value,total()));
    if(select){const part=segments().find(p=>time<p.end)||segments().at(-1);if(part&&selected!==part.scene.id){selected=part.scene.id;renderSelection();}}
    monitor();
  }
  function tick(now) {
    if(!playing)return;
    if(lastTick)time+=(now-lastTick)/1000;lastTick=now;
    if(time>=total())time=0;
    seek(time,true);frame=requestAnimationFrame(tick);
  }
  function selectScene(id) {pause();selected=id;time=startOf(id);renderSelection();monitor();persist();}
  function moveTo(id,target,after) {
    if(id===target||!project.scenes.some(s=>s.id===id)||!project.scenes.some(s=>s.id===target))return;
    commit(()=>{const index=project.scenes.findIndex(s=>s.id===id);const [s]=project.scenes.splice(index,1);const destination=project.scenes.findIndex(s=>s.id===target)+(after?1:0);project.scenes.splice(destination,0,s);selected=id;time=startOf(id);});
  }
  function moveBy(direction) {
    const index=project.scenes.findIndex(s=>s.id===selected),next=index+direction;
    if(index<0||next<0||next>=project.scenes.length)return;
    commit(()=>{[project.scenes[index],project.scenes[next]]=[project.scenes[next],project.scenes[index]];time=startOf(selected);});
  }
  function renderTrack() {
    const track=$('studio-track'),ruler=$('studio-ruler');track.replaceChildren();ruler.replaceChildren();
    $('studio-empty-track').hidden=project.scenes.length>0;$('studio-scroll').hidden=!project.scenes.length;
    $('studio-timeline-inner').style.width=`${Math.max(1,total()*zoom)}px`;
    for(let second=0;second<=total();second+=5){const mark=node('span','studio-tick',stamp(second));mark.style.left=`${second*zoom}px`;ruler.append(mark);}
    project.scenes.forEach((s,index)=>{
      const detail=info(s),card=node('article','scene-card');card.dataset.id=s.id;card.setAttribute('role','listitem');card.tabIndex=0;card.draggable=true;
      card.setAttribute('aria-label',`Szene ${index+1}: ${s.name}`);card.title=`${s.name} · doppelklicken zum Bearbeiten`;
      card.style.width=`${seconds(s)*zoom}px`;
      const head=node('div','scene-card-head');head.append(node('span','',String(index+1).padStart(2,'0')));
      const handle=node('button','scene-handle','⠿');handle.type='button';handle.setAttribute('aria-label',`${s.name} ziehen`);head.append(handle);
      card.append(head,node('strong','scene-card-title',s.name));
      if(detail?.pages?.[0]){const image=node('img','scene-thumb');image.src='data:image/png;base64,'+detail.pages[0];image.alt=`Vorschau ${s.name}`;card.append(image);}else card.append(node('div','scene-thumb pending-thumb','Vorschau …'));
      card.append(node('span','scene-card-meta',`${stamp(seconds(s))} · ${detail?.pages?.length||1} Seite(n)`));
      card.append(node('span','scene-card-effect',s.type==='clock'?'◷ Uhr · live':EFFECT_LABEL(s.options.effect)));
      card.addEventListener('click',()=>selectScene(s.id));card.addEventListener('dblclick',()=>edit(s.id));
      card.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();edit(s.id);}if(e.altKey&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();selected=s.id;moveBy(e.key==='ArrowLeft'?-1:1);}});
      card.addEventListener('dragstart',e=>{pause();e.dataTransfer.setData('text/plain',s.id);e.dataTransfer.effectAllowed='move';card.classList.add('dragging');});
      card.addEventListener('dragend',()=>card.classList.remove('dragging'));
      card.addEventListener('dragover',e=>{e.preventDefault();e.dataTransfer.dropEffect='move';card.classList.add('drop-target');const scroll=$('studio-scroll'),r=scroll.getBoundingClientRect();if(e.clientX<r.left+35)scroll.scrollLeft-=18;if(e.clientX>r.right-35)scroll.scrollLeft+=18;});
      card.addEventListener('dragleave',()=>card.classList.remove('drop-target'));
      card.addEventListener('drop',e=>{e.preventDefault();e.stopPropagation();card.classList.remove('drop-target');const r=card.getBoundingClientRect();moveTo(e.dataTransfer.getData('text/plain'),s.id,e.clientX>r.left+r.width/2);});
      let touchStart=null;
      handle.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;touchStart={x:e.clientX,y:e.clientY};handle.setPointerCapture(e.pointerId);card.classList.add('dragging');});
      handle.addEventListener('pointerup',e=>{if(!touchStart)return;card.classList.remove('dragging');const moved=Math.hypot(e.clientX-touchStart.x,e.clientY-touchStart.y)>10;touchStart=null;if(!moved)return;const target=document.elementFromPoint(e.clientX,e.clientY)?.closest('.scene-card');if(target){const r=target.getBoundingClientRect();moveTo(s.id,target.dataset.id,e.clientX>r.left+r.width/2);}});
      handle.addEventListener('pointercancel',()=>{touchStart=null;card.classList.remove('dragging');});
      track.append(card);
    });
  }
  function EFFECT_LABEL(key){return serverState?.effects?.find(e=>e.value===key)?.label||'Direkt anzeigen';}
  function renderSelection() {
    const current=scene(),index=project.scenes.findIndex(s=>s.id===selected);
    $('studio-selection').hidden=!current;$('studio-selection-empty').hidden=Boolean(current);
    $('studio-selected-number').textContent=current?`${index+1} / ${project.scenes.length}`:'—';
    if(!current)return;
    $('studio-scene-name').value=current.name;$('studio-scene-duration').value=current.options.duration;
    const detail=info(current),ticker=detail?.effective_mode==='ticker';
    $('studio-scene-duration').disabled=ticker;
    $('studio-scene-info').textContent=current.type==='clock'?'Laufende Uhr mit Datum und Logo. Die Dauer gilt für die gesamte Uhrszene.':`${detail?.pages?.length||1} Seite(n) · ${EFFECT_LABEL(current.options.effect)}. `+(ticker?'Die tatsächliche Laufzeit der Laufschrift hängt von der Geschwindigkeit ab.':'Die Standzeit gilt pro Seite; der gewählte Übergang kommt hinzu.');
    $('studio-move-left').disabled=index===0;$('studio-move-right').disabled=index===project.scenes.length-1;
  }
  function render() {
    $('studio-name').value=project.name;$('studio-zoom').value=String(zoom);$('scene-count').textContent=String(project.scenes.length);
    const pageCount=project.scenes.reduce((n,s)=>n+(info(s)?.pages?.length||1),0);
    $('studio-summary').textContent=project.scenes.length?`${project.scenes.length} Szenen · ${pageCount} Seiten · ${stamp(total())} Vorschauzeit${ready?'':' · Vorschau wird geprüft …'}`:'Szenen in die gewünschte Reihenfolge ziehen.';
    $('studio-save').disabled=!project.scenes.length||!ready;
    $('studio-send').disabled=!ready||!project.scenes.length||['queued','running'].includes(serverState?.job?.state);
    $('studio-play').disabled=!ready||!project.scenes.length;
    $('studio-prev').disabled=$('studio-next').disabled=$('studio-seek').disabled=!project.scenes.length;
    $('studio-undo').disabled=!undo.length;$('studio-redo').disabled=!redo.length;
    renderTrack();renderSelection();monitor();
  }
  function edit(id) {
    const current=project.scenes.find(s=>s.id===id);if(!current)return;
    if(current.type==='clock'){
      pause();cancelEdit();editing=id;selected=id;window.MatrixClock.applyOptions(current.options);switchView('clock');
      $('clock-scene-edit-label').textContent=`Bearbeite Uhrszene: ${current.name}`;$('clock-scene-edit-banner').hidden=false;$('clock-add-scene').textContent='Uhrszene in Timeline aktualisieren ✓';return;
    }
    pause();cancelEdit();editing=id;selected=id;applyOptions(current.options);switchView('text');
    $('scene-edit-label').textContent=`Bearbeite Szene: ${current.name}`;$('scene-edit-banner').hidden=false;$('add-scene').textContent='Szene in Timeline aktualisieren ✓';
  }
  function newScene() {cancelEdit();applyOptions({text:'',mode:'auto',size:14,size2:12,split_sizes:false,align:'center',color:'red',speed:10,duration:5,effect:'direct',logo_id:null,logo_position:'left',logo_width:32,logo_style:'original'});switchView('text');$('message').focus();}
  $('add-scene').addEventListener('click',()=>{
    if(!previewValid||previewPending)return;
    const opt=clone(textOptions());let id=project.scenes.some(s=>s.id===editing&&s.type!=='clock')?editing:null;
    if(!id&&project.scenes.length>=30){toast('Maximal 30 Szenen pro Timeline.',true);return;}
    if(!id)id=uid();
    cache.set(id,{pages:previews.slice(),options:opt,effective_mode:measuredLayout?.effective_mode,preview_seconds:previews.length*opt.duration});
    const existed=project.scenes.some(s=>s.id===id);
    commit(()=>{const found=project.scenes.find(s=>s.id===id);if(found)found.options=opt;else project.scenes.push({id,name:opt.text.split('\n')[0].slice(0,50)||'Logo',type:'text',options:opt});selected=id;time=startOf(id);});
    cancelEdit();switchView('studio');toast(existed?'Szene aktualisiert.':'Szene zur Timeline hinzugefügt.');
  });
  $('cancel-scene-edit').addEventListener('click',cancelEdit);
  $('studio-create').addEventListener('click',newScene);$('studio-create-first').addEventListener('click',newScene);
  $('studio-edit').addEventListener('click',()=>edit(selected));
  $('studio-duplicate').addEventListener('click',()=>{if(!scene())return;if(project.scenes.length>=30)return toast('Maximal 30 Szenen.',true);const copy=clone(scene());copy.id=uid();copy.name=(copy.name+' · Kopie').slice(0,80);const cached=info(scene());if(cached)cache.set(copy.id,clone(cached));commit(()=>{project.scenes.splice(project.scenes.findIndex(s=>s.id===selected)+1,0,copy);selected=copy.id;time=startOf(selected);});});
  $('studio-remove').addEventListener('click',()=>{if(scene())commit(()=>{const index=project.scenes.findIndex(s=>s.id===selected);project.scenes.splice(index,1);selected=project.scenes[Math.min(index,project.scenes.length-1)]?.id||null;time=selected?startOf(selected):0;});});
  $('studio-move-left').addEventListener('click',()=>moveBy(-1));$('studio-move-right').addEventListener('click',()=>moveBy(1));
  $('studio-undo').addEventListener('click',()=>restore(undo,redo));$('studio-redo').addEventListener('click',()=>restore(redo,undo));
  $('studio-scene-name').addEventListener('change',()=>{const value=$('studio-scene-name').value.trim();if(scene()&&value&&value!==scene().name)commit(()=>scene().name=value.slice(0,80));else renderSelection();});
  $('studio-scene-duration').addEventListener('change',()=>{const value=Number($('studio-scene-duration').value);if(!Number.isInteger(value)||value<2||value>30){toast('Standzeit: 2 bis 30 Sekunden.',true);renderSelection();return;}if(scene())commit(()=>scene().options.duration=value);});
  for(const id of ['studio-name','studio-scene-name','studio-scene-duration'])$(id).addEventListener('focus',pause);
  $('studio-name').addEventListener('input',()=>{project.name=$('studio-name').value;dirty=true;persist();});
  $('studio-zoom').addEventListener('input',()=>{zoom=Number($('studio-zoom').value);persist();renderTrack();monitor();});
  $('studio-seek').addEventListener('input',()=>{pause();seek(Number($('studio-seek').value),true);});
  $('studio-play').addEventListener('click',()=>{if(playing){pause();return;}if(!ready||!project.scenes.length)return;playing=true;lastTick=0;$('studio-play').textContent='Ⅱ Vorschau pausieren';frame=requestAnimationFrame(tick);});
  $('studio-prev').addEventListener('click',()=>{const i=project.scenes.findIndex(s=>s.id===selected);if(project.scenes.length)selectScene(project.scenes[Math.max(0,i-1)].id);});
  $('studio-next').addEventListener('click',()=>{const i=project.scenes.findIndex(s=>s.id===selected);if(project.scenes.length)selectScene(project.scenes[Math.min(project.scenes.length-1,i+1)].id);});
  $('studio-new').addEventListener('click',()=>{commit(()=>{project={id:null,name:'Meine Timeline',scenes:[]};selected=null;time=0;});cancelEdit();});
  async function save() {
    if(!ready||!project.scenes.length)return;
    if(!project.name.trim())return toast('Bitte einen Projektnamen eingeben.',true);
    const savedSnapshot=JSON.stringify(payload()),owner=project;
    try{const result=await api('/api/timeline/save',payload());if(project===owner){const unchanged=JSON.stringify(payload())===savedSnapshot;project.id=result.id;if(unchanged)dirty=false;persist();}await poll();if(project===owner)$('studio-project-select').value=result.id;toast('Timeline auf dem Raspberry gespeichert.');}catch(error){toast(error.message,true);}
  }
  $('studio-save').addEventListener('click',save);
  $('studio-load').addEventListener('click',async()=>{const id=$('studio-project-select').value;if(!id)return;const revision=version;try{const result=await api('/api/timeline/load',{id});if(revision!==version)return toast('Laden verworfen, weil der Entwurf inzwischen geändert wurde.');commit(()=>{project=result;selected=result.scenes[0]?.id||null;time=0;});dirty=false;cancelEdit();persist();toast('Timeline geladen.');}catch(error){toast(error.message,true);}});
  $('studio-delete-project').addEventListener('click',async()=>{const id=$('studio-project-select').value;if(!id)return;if(!confirm('Dieses gespeicherte Projekt löschen? Der aktuelle Entwurf bleibt erhalten.'))return;try{await api('/api/timeline/delete',{id});if(project.id===id){project.id=null;dirty=true;persist();}await poll();toast('Gespeichertes Projekt entfernt.');}catch(error){toast(error.message,true);}});
  $('studio-project-select').addEventListener('change',()=>{$('studio-load').disabled=$('studio-delete-project').disabled=!$('studio-project-select').value;});
  $('studio-send').addEventListener('click',async()=>{if(!ready)return;try{await api('/api/timeline/send',payload());await poll();toast('Die gesamte Folge wird übertragen.');}catch(error){toast(error.message,true);}});
  document.addEventListener('keydown',e=>{if(view!=='studio'||!(e.ctrlKey||e.metaKey))return;if(e.key.toLowerCase()==='s'){e.preventDefault();save();}if(e.key.toLowerCase()==='z'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();restore(e.shiftKey?redo:undo,e.shiftKey?undo:redo);}});
  document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>{if(button.dataset.view!=='studio')pause();}));
  function onState(value) {
    serverState=value;
    const key=JSON.stringify(value.timelines||[]);
    if(key!==projectListKey){projectListKey=key;const selectedProject=$('studio-project-select').value;const select=$('studio-project-select');select.replaceChildren();const placeholder=node('option','','Gespeichertes Projekt wählen');placeholder.value='';select.append(placeholder);for(const p of value.timelines||[]){const option=node('option','',`${p.name} · ${p.scene_count} Szenen`);option.value=p.id;select.append(option);}select.value=selectedProject||project.id||'';}
    $('studio-load').disabled=$('studio-delete-project').disabled=!$('studio-project-select').value;
    $('studio-send').disabled=!ready||!project.scenes.length||['queued','running'].includes(value.job.state);
  }
  async function addClock(options){
    const current=project.scenes.find(s=>s.id===editing&&s.type==='clock');
    if(!current&&project.scenes.length>=30)throw Error('Maximal 30 Szenen pro Timeline.');
    const duration=Number(options.duration);
    if(!Number.isInteger(duration)||duration<2||duration>30)throw Error('Uhrszene: 2 bis 30 Sekunden.');
    const result=await api('/api/clock/preview',options),opt={...result.options,duration};
    const id=current?.id||uid();
    cache.set(id,{pages:[result.image],options:opt,effective_mode:'clock',preview_seconds:duration});
    commit(()=>{if(current)current.options=opt;else project.scenes.push({id,name:'Uhr · '+$('clock-style').selectedOptions[0].textContent,type:'clock',options:opt});selected=id;time=startOf(id);});
    cancelEdit();switchView('studio');toast(current?'Uhrszene aktualisiert.':'Uhrszene zur Timeline hinzugefügt.');
  }
  document.querySelectorAll('[data-studio-clock]').forEach(button=>button.addEventListener('click',()=>{cancelEdit();window.MatrixClock.applyOptions({...serverState?.clock,duration:5});switchView('clock');}));
  $('clock-cancel-scene-edit').addEventListener('click',cancelEdit);
  setInterval(async()=>{
    if(view!=='studio'||!ready)return;
    const part=segments().find(p=>time<p.end)||segments().at(-1);
    if(part?.scene.type!=='clock')return;
    const revision=version,id=part.scene.id;
    try{const result=await api('/api/clock/preview',part.scene.options);if(version!==revision)return;const detail=cache.get(id);if(detail){detail.pages=[result.image];monitor();}}catch(_){/* validation errors remain in the timeline preview */}
  },1000);
  window.MatrixStudio={onState,addClock};
  render();persist();schedulePreview();if(state)onState(state);
})();
