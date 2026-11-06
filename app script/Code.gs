function include_(name) { return HtmlService.createHtmlOutputFromFile(name).getContent(); }
function doGet() {
  try {
    identity_();
    return HtmlService.createTemplateFromFile('Index').evaluate().setTitle('BVT · Master Data').addMetaTag('viewport','width=device-width, initial-scale=1');
  } catch(e) {
    const out=HtmlService.createHtmlOutput('<h2>Acceso a BVT MDM</h2><p></p>');
    // Only fixed messages reach this page, no dynamic HTML from user input.
    out.append('<p>Usa una cuenta de buenavidatrading.com y comprueba la configuración con el propietario.</p>');return out;
  }
}
/** Single RPC entry point. All helpers are private to google.script.run. */
function api(action,payload) {
  try {
    const email=identity_(),p=payload||{};
    if(action==='bootstrap') {
      const nonce=uuid_();CacheService.getScriptCache().put('csrf:'+email+':'+nonce,'1',21600);
      return {ok:true,data:{email:email,nonce:nonce,today:Utilities.formatDate(new Date(),'Europe/Madrid','yyyy-MM-dd'),lookups:rows_('Lookups'),counts:{companies:rows_('Companies').filter(r=>active_(r.active)).length,customers:rows_('Customers').filter(r=>active_(r.active)).length,vendors:rows_('Vendors').filter(r=>active_(r.active)).length,priceLists:rows_('PriceLists').filter(r=>active_(r.active)).length}}};
    }
    const read={list:listParties_,detail:detailParty_,lines:listLines_,importProgress:(p)=>jobProgress_(importJob_(p.id,email))};
    if(Object.prototype.hasOwnProperty.call(read,action))return {ok:true,data:read[action](p)};
    const write={saveParty:saveParty_,setActive:setPartyActive_,deleteParty:deleteParty_,makeDefault:makeDefault_,saveChild:saveChild_,childAction:childAction_,editLine:editLine_,activate:activateList_,deleteDraft:deleteDraft_,upload:uploadImport_,preview:previewImport_,startValidation:startValidation_,validateChunk:validateChunk_,commit:commitImport_,cancelImport:cancelImport_};
    if(!Object.prototype.hasOwnProperty.call(write,action))fail_('Acción no válida.');
    if(typeof p.nonce!=='string'||!CacheService.getScriptCache().get('csrf:'+email+':'+p.nonce))fail_('La sesión de la página caducó. Recarga antes de guardar.');
    return {ok:true,data:lock_(()=>write[action](p,email))};
  } catch(e) {
    if(!e.publicMessage){const id=uuid_();console.error('MDM '+id+': '+String(e.message).slice(0,1000));return {ok:false,error:'No se pudo completar la operación. Recarga o contacta al propietario. Referencia: '+id,field:''};}
    return {ok:false,error:e.publicMessage,field:e.field||''};
  }
}
