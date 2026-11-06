function makeDefault_(p,email) {
  const row=party_('company',p.id,true);version_(row,p.version);
  rows_('Companies').forEach(r=>{if(active_(r.is_default)!==(r.id===row.id))persist_('Companies',r,changed_(r,{is_default:r.id===row.id},email),email,'make_default');});
  return get_('Companies',row.id);
}
