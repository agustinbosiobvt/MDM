function installBackupTrigger() {
  ownerOnly_();
  ScriptApp.getProjectTriggers().filter(t=>t.getHandlerFunction()==='nightlyBackup').forEach(t=>ScriptApp.deleteTrigger(t));
  const trigger=ScriptApp.newTrigger('nightlyBackup').timeBased().atHour(2).everyDays(1).inTimezone('Europe/Madrid').create();
  props_().setProperty('MDM_BACKUP_TRIGGER_ID',trigger.getUniqueId());
  console.log('Copia nocturna instalada: entre 02:00 y 03:00, Europe/Madrid.');
}
/** Master is copied nightly; line files with edits are snapshotted as immutable revisions. */
function nightlyBackup(event) {
  // Time triggers have no active user. Verify the installed trigger and effective owner.
  const active=String(Session.getActiveUser().getEmail()||'').toLowerCase();
  const expected=props_().getProperty('MDM_OWNER_EMAIL');
  const isTrigger=event&&String(event.triggerUid)===props_().getProperty('MDM_BACKUP_TRIGGER_ID');
  const email=active?ownerOnly_():isTrigger&&String(Session.getEffectiveUser().getEmail()).toLowerCase()===expected?expected:'';
  if(!email)fail_('Solo el propietario o el activador instalado pueden crear copias.');
  return lock_(function(){
    const backups=folder_('MDM_BACKUPS_FOLDER_ID'),stamp=Utilities.formatDate(new Date(),'Europe/Madrid','yyyy-MM-dd_HHmmss');
    const copy=DriveApp.getFileById(props_().getProperty('MDM_DATA_ID')).makeCopy('MDM_Data_'+stamp,backups);
    const masters=[],iterator=backups.getFiles();while(iterator.hasNext()){const file=iterator.next();if(file.getName().startsWith('MDM_Data_'))masters.push(file);}
    masters.sort((a,b)=>b.getDateCreated().getTime()-a.getDateCreated().getTime());masters.slice(30).forEach(f=>f.setTrashed(true));
    // Full business data: one frozen copy per changed price-list version. Old copies
    // remain available to restore any of the retained master backups.
    const lists=rows_('PriceLists'),lineCopies=[];
    lists.forEach(pl=>{
      const key='Lines_'+pl.id+'_v'+pl.version;
      if(!backups.getFilesByName(key).hasNext()){DriveApp.getFileById(pl.lines_file_id).makeCopy(key,backups);lineCopies.push(pl.id);}
    });
    rows_('ImportJobs').filter(j=>!['committed','cancelled','expired'].includes(j.status)&&j.expires_at<now_()).forEach(j=>{
      // Never trash a staging file already published by a partially retried commit.
      const published=lists.some(pl=>pl.id===j.id);
      if(!published)[j.staging_file_id,j.source_file_id].filter(Boolean).forEach(id=>DriveApp.getFileById(id).setTrashed(true));
      if(j.converted_file_id)DriveApp.getFileById(j.converted_file_id).setTrashed(true);
      replace_('ImportJobs',changed_(j,{status:published?'committed':'expired',price_list_id:published?j.id:''},email));
    });
    audit_(email,'backup','System',copy.getId(),null,{master:copy.getId(),line_snapshots:lineCopies.length});return {masterId:copy.getId(),newLineSnapshots:lineCopies.length};
  });
}
