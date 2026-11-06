function fail_(message, field) { const e = new Error(message); e.publicMessage = message; e.field = field || ''; throw e; }
function props_() { return PropertiesService.getScriptProperties(); }
function now_() { return new Date().toISOString(); }
function uuid_() { return Utilities.getUuid(); }
function identity_() {
  const email = String(Session.getActiveUser().getEmail() || '').toLowerCase();
  if (!email || email.split('@')[1] !== MDM.domain) fail_('Acceso denegado. Usa tu cuenta de ' + MDM.domain + '. Google debe permitir leer tu correo.');
  return email;
}
function ownerOnly_() {
  const email = identity_();
  if (email !== String(Session.getEffectiveUser().getEmail()).toLowerCase()) fail_('Ejecuta esta función desde el editor con la cuenta propietaria.');
  const owner = props_().getProperty('MDM_OWNER_EMAIL');
  if (owner && owner !== email) fail_('Solo la cuenta que instaló MDM puede ejecutar esta función.');
  return email;
}
function db_() {
  const id = props_().getProperty('MDM_DATA_ID');
  if (!id) fail_('Falta configurar la base. El propietario debe ejecutar setup.');
  return SpreadsheetApp.openById(id);
}
function lock_(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) fail_('Hay otra operación en curso. Inténtalo de nuevo.');
  try { return fn(); } finally { lock.releaseLock(); }
}
function textCell_(value) {
  if (value == null) return '';
  if (typeof value === 'object') value = JSON.stringify(value);
  if (typeof value === 'string') {
    if (value.length > 45000) fail_('Un valor supera el tamaño permitido por celda (45.000 caracteres).');
    // Escape also leading apostrophes, preserving exactly one on read.
    return /^[=+\-@'\t\r\n]/.test(value) ? "'" + value : value;
  }
  return value;
}
function readSheet_(sheet) {
  if (sheet.getLastRow() < 2) return [];
  const data = sheet.getDataRange().getValues(), headers = data.shift();
  return data.filter(row => row.some(v => v !== '')).map(row => {
    const out = {}; headers.forEach((h,i) => out[h] = row[i] instanceof Date ? row[i].toISOString() : row[i]); return out;
  });
}
function rows_(table) { const s = db_().getSheetByName(table); if (!s) fail_('Falta la hoja ' + table + '. Ejecuta setup.'); return readSheet_(s); }
function get_(table,id) { const row = rows_(table).find(r => r.id === id); if (!row) fail_('Registro no encontrado.'); return row; }
function initSheet_(book,name,headers) {
  const s = book.getSheetByName(name) || book.insertSheet(name);
  if (!s.getLastRow()) {
    if (s.getMaxColumns() < headers.length) s.insertColumnsAfter(s.getMaxColumns(),headers.length-s.getMaxColumns());
    s.getRange(1,1,1,headers.length).setValues([headers]).setBackground('#173e45').setFontColor('#ffffff').setFontWeight('bold');
    s.setFrozenRows(1); s.setHiddenGridlines(true); s.setColumnWidths(1,headers.length,160);
  } else {
    const actual = s.getRange(1,1,1,s.getLastColumn()).getValues()[0];
    if (JSON.stringify(actual) !== JSON.stringify(headers)) fail_('La estructura de ' + name + ' no corresponde a esta versión. No se sobrescribió.');
  }
  return s;
}
function appendRows_(sheet,headers,objects) {
  if (!objects.length) return;
  const values = objects.map(o => headers.map(h => textCell_(o[h])));
  const end = sheet.getLastRow() + objects.length;
  if (end > sheet.getMaxRows()) sheet.insertRowsAfter(sheet.getMaxRows(),end-sheet.getMaxRows());
  const range = sheet.getRange(sheet.getLastRow()+1,1,values.length,headers.length);
  range.setNumberFormat('@'); range.setValues(values);
}
function append_(table,row) { appendRows_(db_().getSheetByName(table),SCHEMA[table],[row]); }
function replace_(table,row) {
  const sheet = db_().getSheetByName(table), ids = sheet.getRange(2,1,Math.max(1,sheet.getLastRow()-1),1).getValues();
  const index = ids.findIndex(v => v[0] === row.id);
  if (index < 0) fail_('Registro no encontrado.');
  const range = sheet.getRange(index+2,1,1,SCHEMA[table].length);
  range.setNumberFormat('@'); range.setValues([SCHEMA[table].map(h => textCell_(row[h]))]);
}
function removeRow_(table,id) {
  const s = db_().getSheetByName(table), list = rows_(table), i = list.findIndex(r=>r.id===id);
  if(i<0) fail_('Registro no encontrado.'); s.deleteRow(i+2);
}
function newRow_(data,email) { const time=now_(); return Object.assign({},data,{id:uuid_(),created_at:time,created_by:email,updated_at:time,updated_by:email,active:true,version:1}); }
function changed_(old,data,email) { return Object.assign({},old,data,{updated_at:now_(),updated_by:email,version:Number(old.version)+1}); }
function version_(old,expected) { if(Number(old.version)!==Number(expected)) fail_('Otra persona modificó este registro. Recarga e inténtalo de nuevo.'); }
function audit_(email,action,table,id,old,value) {
  append_('AuditLog',{id:uuid_(),timestamp:now_(),user_email:email,action:action,entity:table,entity_id:id,old_values:old?JSON.stringify(old):'',new_values:value?JSON.stringify(value):''});
}
function persist_(table,old,row,email,action) {
  // Validate audit sizes before any write; Sheets is not a transactional database.
  textCell_(JSON.stringify(old)); textCell_(JSON.stringify(row));
  if(old) replace_(table,row); else append_(table,row);
  audit_(email,action || (old?'update':'create'),table,row.id,old,row); return row;
}
function active_(v) { return v===true || String(v).toUpperCase()==='TRUE'; }
function json_(v,fallback) { if(typeof v==='object' && v!==null) return v; try{return JSON.parse(v);}catch(e){return fallback;} }
function lookup_(kind) { return rows_('Lookups').filter(r=>r.kind===kind); }
function page_(list,p) {
  const page=Math.max(1,Math.floor(Number(p.page)||1));
  return {items:list.slice((page-1)*MDM.pageSize,page*MDM.pageSize),total:list.length,page:page,pageSize:MDM.pageSize};
}
