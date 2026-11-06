function versions_(p) {
  party_(p.type,p.id,false);
  const today=Utilities.formatDate(new Date(),'Europe/Madrid','yyyy-MM-dd');
  return rows_('PriceLists').filter(r=>r.owner_id===p.id&&r.owner_type===p.type&&active_(r.active)).sort((a,b)=>Number(b.revision)-Number(a.revision)).map(r=>Object.assign({},r,{effective_status:r.status==='active'&&r.valid_to&&r.valid_to<today?'expired':r.status}));
}
function priceList_(id) { const pl=get_('PriceLists',id);if(!active_(pl.active))fail_('Lista retirada.');return pl; }
function lineSheet_(pl) { return SpreadsheetApp.openById(pl.lines_file_id).getSheetByName('Lines'); }
function duplicateMap_(lines) {
  const map={};lines.filter(r=>active_(r.active)).forEach(r=>{map[r.dup_key]=(map[r.dup_key]||0)+1;});return map;
}
function listLines_(p) {
  const pl=priceList_(p.id),lines=readSheet_(lineSheet_(pl)),duplicates=duplicateMap_(lines);
  const q=str_(p.q,100,false,'q').toLowerCase();
  const facets={brands:[...new Set(lines.filter(r=>active_(r.active)).map(r=>r.brand))].sort(),categories:[...new Set(lines.filter(r=>active_(r.active)).map(r=>r.category))].sort()};
  const all=lines.map(r=>{
    const issues=json_(r.issues,[]).filter(x=>x!=='duplicate_key');
    const duplicate=active_(r.active)&&duplicates[r.dup_key]>1;
    return Object.assign({},r,{issues:issues,duplicate:duplicate,line_status:!active_(r.active)?'excluded':duplicate?'duplicate':issues.length?'warning':'ok'});
  });
  let filtered=all.filter(r=>(p.show==='excluded'?!active_(r.active):active_(r.active))&&(!p.show||p.show==='all'||r.line_status===p.show)&&(!q||[r.ean,r.upc,r.asin,r.vendor_sku,r.description].some(v=>String(v).toLowerCase().includes(q)))&&(!p.brand||(p.brand==='__none__'?!r.brand:r.brand===p.brand))&&(!p.category||(p.category==='__none__'?!r.category:r.category===p.category)));
  const sort=['source_row','ean','asin','description','brand','category'].includes(p.sort)?p.sort:'source_row';
  filtered.sort((a,b)=>(sort==='source_row'?Number(a[sort])-Number(b[sort]):String(a[sort]).localeCompare(String(b[sort])))*(p.order==='desc'?-1:1));
  return Object.assign(page_(filtered,p),{priceList:pl,facets:facets,priceColumns:json_(pl.price_columns,[]),duplicateGroups:Object.values(duplicates).filter(n=>n>1).length,excluded:all.filter(r=>!active_(r.active)).length,warnings:all.filter(r=>r.issues.length).length});
}
function editLine_(p,email) {
  const pl=priceList_(p.price_list_id);party_(pl.owner_type,pl.owner_id,true);
  const sheet=lineSheet_(pl),headers=sheet.getRange(1,1,1,sheet.getLastColumn()).getValues()[0],lines=readSheet_(sheet),index=lines.findIndex(r=>r.id===p.id);
  if(index<0)fail_('Línea no encontrada.');const old=lines[index];version_(old,p.version);
  let data;
  if(p.action==='exclude'||p.action==='include') {
    if(pl.status!=='draft')fail_('Solo se pueden excluir o incluir líneas de un borrador.');
    data={active:p.action==='include'};
  } else {
    data={brand:str_(p.brand,100,false,'brand'),category:str_(p.category,100,false,'category')};
  }
  const row=changed_(old,data,email);
  // Do not duplicate 45K raw rows/prices in each audit record: record changed attributes.
  const before={price_list_id:pl.id,source_row:old.source_row,version:old.version},after={price_list_id:pl.id,source_row:row.source_row,version:row.version};
  Object.keys(data).forEach(k=>{before[k]=old[k];after[k]=row[k];});
  sheet.getRange(index+2,1,1,headers.length).setNumberFormat('@').setValues([headers.map(h=>textCell_(row[h]))]);
  audit_(email,p.action||'edit_line','PriceListLine',row.id,before,after);
  persist_('PriceLists',pl,changed_(pl,{},email),email,'line_update');return row;
}
function activateList_(p,email) {
  const pl=priceList_(p.id);party_(pl.owner_type,pl.owner_id,true);version_(pl,p.version);
  if(pl.status!=='draft')fail_('Solo se puede activar un borrador.');
  const lines=readSheet_(lineSheet_(pl)).filter(r=>active_(r.active));
  if(!lines.length)fail_('No hay líneas incluidas.');
  if(Object.values(duplicateMap_(lines)).some(n=>n>1))fail_('Excluye las líneas duplicadas antes de activar.');
  const today=Utilities.formatDate(new Date(),'Europe/Madrid','yyyy-MM-dd');
  if(pl.valid_to&&pl.valid_to<today)fail_('La fecha final ya ha pasado. Importa una versión con fechas vigentes.');
  const overlaps=(a,b)=>(!a.valid_to||a.valid_to>=b.valid_from)&&(!b.valid_to||b.valid_to>=a.valid_from);
  rows_('PriceLists').filter(r=>r.id!==pl.id&&r.owner_id===pl.owner_id&&r.owner_type===pl.owner_type&&r.currency===pl.currency&&r.status==='active'&&active_(r.active)&&overlaps(r,pl)).forEach(r=>persist_('PriceLists',r,changed_(r,{status:'expired'},email),email,'expire'));
  return persist_('PriceLists',pl,changed_(pl,{status:'active'},email),email,'activate');
}
function deleteDraft_(p,email) {
  const old=priceList_(p.id);party_(old.owner_type,old.owner_id,true);version_(old,p.version);
  if(old.status!=='draft'||p.confirm!==old.name)fail_('Solo se retiran borradores. Escribe su nombre exacto.');
  return persist_('PriceLists',old,changed_(old,{active:false},email),email,'remove_draft');
}
