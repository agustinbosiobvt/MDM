/** Set MDM_DATA_ID in Script Properties to the converted MDM_Data.xlsx ID before setup. */
function setup() {
  const email=ownerOnly_();
  return lock_(function(){
    const p=props_();
    if(!p.getProperty('MDM_FOLDER_ID'))p.setProperty('MDM_FOLDER_ID',DriveApp.createFolder('MDM Data').getId());
    const folder=DriveApp.getFolderById(p.getProperty('MDM_FOLDER_ID'));
    [['MDM_LISTS_FOLDER_ID','PriceLists'],['MDM_BACKUPS_FOLDER_ID','Backups']].forEach(x=>{
      if(!p.getProperty(x[0]))p.setProperty(x[0],folder.createFolder(x[1]).getId());
    });
    const lists=DriveApp.getFolderById(p.getProperty('MDM_LISTS_FOLDER_ID'));
    if(!p.getProperty('MDM_SOURCES_FOLDER_ID'))p.setProperty('MDM_SOURCES_FOLDER_ID',lists.createFolder('Sources').getId());
    if(!p.getProperty('MDM_STAGING_FOLDER_ID'))p.setProperty('MDM_STAGING_FOLDER_ID',folder.createFolder('Import staging').getId());
    if(!p.getProperty('MDM_DATA_ID')) {
      const book=SpreadsheetApp.create('MDM_Data');
      p.setProperty('MDM_DATA_ID',book.getId());
    }
    const book=db_();book.setSpreadsheetTimeZone('Europe/Madrid');book.setSpreadsheetLocale('en_US');
    Object.keys(SCHEMA).forEach(name=>initSheet_(book,name,SCHEMA[name]));
    book.getSheets().filter(s=>!SCHEMA[s.getName()]&&!s.getLastRow()).forEach(s=>book.deleteSheet(s));
    if(!rows_('Lookups').length)appendRows_(book.getSheetByName('Lookups'),SCHEMA.Lookups,SEED_LOOKUPS);
    DriveApp.getFileById(book.getId()).moveTo(folder);
    p.setProperty('MDM_OWNER_EMAIL',email);p.setProperty('MDM_SCHEMA_VERSION','1');
    audit_(email,'setup','System',book.getId(),null,{schema:1});
    console.log('Base configurada: '+book.getUrl());
    return {spreadsheetUrl:book.getUrl(),folderUrl:folder.getUrl()};
  });
}
