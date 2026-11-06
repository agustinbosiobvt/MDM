function ownerTable_(type) { if(!Object.prototype.hasOwnProperty.call(OWNER_TABLE,type))fail_('Tipo de registro no válido.');return OWNER_TABLE[type]; }
function party_(type,id,requireActive) { const r=get_(ownerTable_(type),id);if(requireActive&&!active_(r.active))fail_('El registro está retirado. Reactívalo antes de editar.');return r; }
function listParties_(p) {
  const table=ownerTable_(p.type),q=str_(p.q,100,false,'q').toLowerCase();
  let list=rows_(table).filter(r=>active_(r.active)===(p.show!=='removed')&&(!q||[r.code,r.legal_name,r.trade_name].some(v=>String(v).toLowerCase().includes(q))));
  const sort=['code','legal_name','country_code','status'].includes(p.sort)?p.sort:'code';
  list.sort((a,b)=>String(a[sort]||'').localeCompare(String(b[sort]||''))*(p.order==='desc'?-1:1));return page_(list,p);
}
function detailParty_(p) {
  const row=party_(p.type,p.id,false),match=r=>r.owner_id===p.id&&r.owner_type===p.type;
  return {record:row,addresses:rows_('Addresses').filter(match),contacts:rows_('Contacts').filter(match),vendorCodes:p.type==='customer'?rows_('VendorCodes').filter(match):[],priceLists:p.type!=='company'?versions_(p):[]};
}
function validateParty_(type,data) {
  const allowed=SCHEMA[ownerTable_(type)].filter(k=>!COMMON.includes(k)&&k!=='is_default'); const out={};
  Object.keys(data).forEach(k=>{if(!allowed.includes(k))fail_('Campo no permitido: '+k,k);});
  allowed.forEach(k=>{if(k!=='lead_time_days'&&k!=='moq')out[k]=str_(data[k],FIELD_LIMITS[k]||200,['code','legal_name','country_code'].includes(k),k);});
  out.code=out.code.toUpperCase();if(!/^[A-Z0-9][A-Z0-9_-]{0,19}$/.test(out.code))fail_('Usa letras, números, guion o guion bajo.', 'code');
  out.country_code=lookupCode_('country',out.country_code,true,'country_code');
  if(type!=='company') {
    out.status=enum_(out.status||'active',['active','on_hold','blocked'],'status');
    out.default_currency=lookupCode_('currency',out.default_currency,true,'default_currency');
    out.incoterm_code=lookupCode_('incoterm',out.incoterm_code,false,'incoterm_code');
    out.payment_term_code=lookupCode_('payment_term',out.payment_term_code,false,'payment_term_code');
  }
  if(type!=='customer'){out.eori=out.eori.toUpperCase().replace(/\s/g,'');if(out.eori&&!/^[A-Z]{2}[A-Z0-9]{1,15}$/.test(out.eori))fail_('EORI no válido.','eori');}
  if(type==='vendor'){out.lead_time_days=integer_(data.lead_time_days,0,730,'lead_time_days');out.moq=integer_(data.moq,1,2147483647,'moq');}
  return out;
}
function saveParty_(p,email) {
  const table=ownerTable_(p.type),old=p.id?party_(p.type,p.id,true):null;if(old)version_(old,p.version);
  const data=validateParty_(p.type,p.data||{});
  Object.values(OWNER_TABLE).forEach(t=>{if(rows_(t).some(r=>r.code===data.code&&r.id!==(old&&old.id)))fail_('Ese código ya existe, incluso entre los registros retirados.','code');});
  if(p.type==='company')data.is_default=old?active_(old.is_default):!rows_('Companies').some(r=>active_(r.is_default));
  const row=old?changed_(old,data,email):newRow_(data,email);return persist_(table,old,row,email);
}
function setPartyActive_(p,email) {
  if(typeof p.active!=='boolean')fail_('Estado de registro no válido.');
  const table=ownerTable_(p.type),old=party_(p.type,p.id,false);version_(old,p.version);
  if(p.type==='company'&&active_(old.is_default)&&!p.active)fail_('Elige otra empresa predeterminada antes de retirar esta.');
  return persist_(table,old,changed_(old,{active:p.active===true},email),email,p.active?'reactivate':'remove');
}
function deleteParty_(p,email) {
  const table=ownerTable_(p.type),old=party_(p.type,p.id,false);version_(old,p.version);
  if(active_(old.active)||p.confirm!==old.code)fail_('Retira el registro y escribe su código exacto para eliminarlo.');
  if(p.type==='company'&&active_(old.is_default))fail_('No se puede eliminar la empresa predeterminada.');
  if(rows_('PriceLists').some(r=>r.owner_id===p.id))fail_('Este registro ha tenido listas de precios. Debe conservarse.');
  ['Addresses','Contacts','VendorCodes','MappingTemplates'].forEach(t=>rows_(t).filter(r=>r.owner_id===p.id).forEach(r=>{audit_(email,'permanent_delete',t,r.id,r,null);removeRow_(t,r.id);}));
  audit_(email,'permanent_delete',table,p.id,old,null);removeRow_(table,p.id);return {deleted:true};
}
function childTable_(kind) { if(!['Addresses','Contacts','VendorCodes'].includes(kind))fail_('Sección no válida.');return kind; }
function saveChild_(p,email) {
  party_(p.type,p.owner_id,true);const table=childTable_(p.table),old=p.id?get_(table,p.id):null;
  if(old){if(old.owner_id!==p.owner_id||old.owner_type!==p.type)fail_('Registro no encontrado.');version_(old,p.version);}
  if(table==='VendorCodes'&&p.type!=='customer')fail_('Los códigos Amazon pertenecen a clientes.');
  const data={owner_id:p.owner_id,owner_type:p.type};
  const fields=SCHEMA[table].filter(k=>!COMMON.includes(k)&&!['owner_id','owner_type'].includes(k));
  Object.keys(p.data||{}).forEach(k=>{if(!fields.includes(k))fail_('Campo no permitido: '+k,k);});
  fields.forEach(k=>{data[k]=k==='is_primary'?p.data[k]===true:str_(p.data[k],FIELD_LIMITS[k]||200,['line1','city','name','parent_code','child_code'].includes(k),k);});
  if(table==='Addresses') {
    const types={company:['registered','billing','warehouse'],customer:['billing','ship_to'],vendor:['billing','pick_up','factory']};
    data.address_type=enum_(data.address_type,types[p.type],'address_type');data.country_code=lookupCode_('country',data.country_code,true,'country_code');
  }
  if(table==='Contacts') {
    if(data.email&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email))fail_('Correo no válido.','email');
    if(p.type==='vendor')data.contact_role=enum_(data.contact_role||'other',['sales','logistics','quality','other'],'contact_role');else data.contact_role='';
    const siblings=rows_(table).filter(r=>r.owner_id===p.owner_id&&active_(r.active)&&r.id!==p.id);
    data.is_primary=old?active_(old.is_primary):!siblings.length;
  }
  if(table==='VendorCodes') {
    ['parent_code','child_code'].forEach(k=>{data[k]=data[k].toUpperCase();if(!/^[A-Z0-9_-]+$/.test(data[k]))fail_('Código no válido.',k);});
    data.destination_country=lookupCode_('country',data.destination_country,false,'destination_country');
    if(rows_(table).some(r=>r.id!==p.id&&active_(r.active)&&r.parent_code===data.parent_code&&r.child_code===data.child_code))fail_('Ese par de códigos ya está asignado.','parent_code');
  }
  return persist_(table,old,old?changed_(old,data,email):newRow_(data,email),email);
}
function childAction_(p,email) {
  const table=childTable_(p.table),old=get_(table,p.id);party_(old.owner_type,old.owner_id,true);version_(old,p.version);
  if(p.action==='primary') {
    if(table!=='Contacts'||!active_(old.active))fail_('Contacto no disponible.');
    rows_(table).filter(r=>r.owner_id===old.owner_id&&active_(r.active)).forEach(r=>{if(active_(r.is_primary)!==(r.id===old.id))persist_(table,r,changed_(r,{is_primary:r.id===old.id},email),email,'primary');});return {ok:true};
  }
  if(!['remove','reactivate'].includes(p.action))fail_('Acción no válida.');
  const turnOn=p.action==='reactivate';
  if(turnOn&&table==='VendorCodes'&&rows_(table).some(r=>r.id!==old.id&&active_(r.active)&&r.parent_code===old.parent_code&&r.child_code===old.child_code))fail_('Ese par de códigos ya está asignado.');
  const data={active:turnOn};
  if(table==='Contacts')data.is_primary=turnOn?!rows_(table).some(r=>r.owner_id===old.owner_id&&active_(r.active)&&active_(r.is_primary)):false;
  const out=persist_(table,old,changed_(old,data,email),email,p.action);
  if(table==='Contacts'&&!turnOn&&active_(old.is_primary)) {
    const next=rows_(table).find(r=>r.owner_id===old.owner_id&&active_(r.active));if(next)persist_(table,next,changed_(next,{is_primary:true},email),email,'primary');
  }
  return out;
}
