function letter_(n) { let out='';for(n++;n>0;n=Math.floor((n-1)/26))out=String.fromCharCode(65+(n-1)%26)+out;return out; }
function column_(v) {
  if(typeof v==='number')return integer_(v,0,199,'column');
  const s=String(v||'').trim().toUpperCase();if(!/^[A-Z]{1,3}$/.test(s))fail_('Columna no válida.');
  let n=0;s.split('').forEach(c=>n=n*26+c.charCodeAt(0)-64);if(n>200)fail_('Máximo 200 columnas.');return n-1;
}
function importJob_(id,email) { const j=get_('ImportJobs',id);if(j.created_by!==email)fail_('La importación pertenece a otra persona.');if(j.expires_at<now_()&&!['committed','cancelled'].includes(j.status))fail_('La importación caducó. Vuelve a cargar el archivo.');return j; }
function folder_(key) { return DriveApp.getFolderById(props_().getProperty(key)); }
/** Strip executable XLSX formulas before conversion; use cached results as provided. */
function checkZip_(bytes) {
  const u=i=>(bytes[i]+256)%256,word=i=>u(i)+u(i+1)*256,dword=i=>word(i)+word(i+2)*65536;
  let end=-1;for(let i=bytes.length-22;i>=Math.max(0,bytes.length-65557);i--){if(dword(i)===0x06054b50){end=i;break;}}
  if(end<0||word(end+4)!==0||word(end+6)!==0)fail_('Contenedor ZIP no admitido.');
  const count=word(end+10);let cursor=dword(end+16),total=0;
  if(count>3000||count===65535)fail_('El Excel contiene demasiados componentes.');
  for(let n=0;n<count;n++) {
    if(cursor+46>bytes.length||dword(cursor)!==0x02014b50)fail_('Directorio ZIP inválido.');
    const flags=word(cursor+8),method=word(cursor+10),size=dword(cursor+24);
    if((flags&1)||![0,8].includes(method)||size===0xffffffff)fail_('No se admiten Excel cifrados, ZIP64 o compresión especial.');
    total+=size;if(total>100*1024*1024)fail_('El Excel descomprimido supera 100 MB.');
    cursor+=46+word(cursor+28)+word(cursor+30)+word(cursor+32);
  }
}
function safeXlsx_(blob) {
  checkZip_(blob.getBytes());
  let total=0;const entries=Utilities.unzip(blob.copyBlob().setContentType('application/zip')),out=[];
  entries.forEach(entry=>{
    const name=entry.getName();total+=entry.getBytes().length;
    if(total>100*1024*1024||entries.length>3000)fail_('El Excel descomprimido es demasiado grande.');
    if(/vbaProject|macrosheet|activeX/i.test(name))fail_('No se admiten macros o contenido activo.');
    if(/externalLinks\/|calcChain\.xml$/i.test(name))return;
    if(/\.xml$|\.rels$/i.test(name)) {
      let xml=entry.getDataAsString();
      if(/<!DOCTYPE|<!ENTITY/i.test(xml))fail_('XML no admitido.');
      if(/xl\/worksheets\/.*\.xml$/i.test(name))xml=xml.replace(/<(?:\w+:)?f\b[^>]*\/>/g,'').replace(/<(?:\w+:)?f\b[^>]*>[\s\S]*?<\/(?:\w+:)?f>/g,'');
      xml=xml.replace(/<externalReferences\b[^>]*>[\s\S]*?<\/externalReferences>/g,'');
      if(/\.rels$/i.test(name))xml=xml.replace(/<Relationship\b(?=[^>]*(?:TargetMode="External"|Type="[^"]*(?:externalLink|calcChain)"))[^>]*\/>/g,'');
      if(name==='[Content_Types].xml')xml=xml.replace(/<Override\b(?=[^>]*PartName="[^"]*(?:externalLinks\/|calcChain\.xml))[^>]*\/>/g,'');
      entry=Utilities.newBlob(xml,'application/xml',name);
    }
    out.push(entry);
  });
  if(!out.some(x=>x.getName()==='xl/workbook.xml'))fail_('El archivo no es un libro XLSX válido.');
  return Utilities.zip(out,'safe.xlsx').setContentType('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
}
function uploadImport_(p,email) {
  party_(p.type,p.owner_id,true);if(p.type==='company')fail_('Las empresas no tienen listas de precios.');
  const name=str_(p.name,255,true,'name'),ext=name.split('.').pop().toLowerCase();
  if(!['xlsx','csv'].includes(ext))fail_('Solo se admiten .xlsx y .csv.');
  if(typeof p.base64!=='string'||p.base64.length>Math.ceil(MDM.maxBytes/3)*4+8)fail_('El archivo supera 20 MB.');
  const bytes=Utilities.base64Decode(p.base64);if(!bytes.length||bytes.length>MDM.maxBytes)fail_('Archivo vacío o mayor de 20 MB.');
  const allowedMime=ext==='xlsx'?['','application/octet-stream','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:['','text/csv','application/csv','application/vnd.ms-excel','text/plain','application/octet-stream'];
  if(!allowedMime.includes(String(p.mime||'')))fail_('El tipo de archivo no coincide con su extensión.');
  if(ext==='xlsx'&&(bytes[0]!==80||bytes[1]!==75))fail_('El contenido no corresponde a un XLSX.');
  const hash=sha_(bytes),token=uuid_(),blob=Utilities.newBlob(bytes,ext==='xlsx'?'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':'text/csv',name);
  let source,book,convertedId;
  try {
    // Sanitize before creating any Google spreadsheet, so source formulas never execute.
    const safe=ext==='xlsx'?safeXlsx_(blob):null;
    source=folder_('MDM_SOURCES_FOLDER_ID').createFile(blob).setName(token+'__'+name);
    if(ext==='xlsx') {
      const converted=Drive.Files.create({name:'Import '+token,mimeType:'application/vnd.google-apps.spreadsheet',parents:[props_().getProperty('MDM_STAGING_FOLDER_ID')]},safe,{fields:'id'});
      convertedId=converted.id;book=SpreadsheetApp.openById(convertedId);
    } else {
      const text=blob.getDataAsString('UTF-8').replace(/^\uFEFF/,'');if(text.includes('\u0000'))fail_('CSV inválido. Guarda el archivo con UTF-8.');
      const first=text.split(/\r?\n/)[0],sep=(first.match(/;/g)||[]).length>(first.match(/,/g)||[]).length?';':',';
      const values=Utilities.parseCsv(text,sep);if(values.length>MDM.maxRows+1000)fail_('Máximo 50.000 filas de datos.');
      const width=Math.max.apply(null,values.map(r=>r.length));if(width>200)fail_('Máximo 200 columnas.');
      book=SpreadsheetApp.create('Import '+token);convertedId=book.getId();const s=book.getSheets()[0];s.setName('CSV');
      if(s.getMaxColumns()<width)s.insertColumnsAfter(s.getMaxColumns(),width-s.getMaxColumns());if(s.getMaxRows()<values.length)s.insertRowsAfter(s.getMaxRows(),values.length-s.getMaxRows());
      s.getRange(1,1,values.length,width).setNumberFormat('@').setValues(values.map(r=>Array.from({length:width},(_,i)=>textCell_(r[i]||''))));
      DriveApp.getFileById(convertedId).moveTo(folder_('MDM_STAGING_FOLDER_ID'));
    }
    if(book.getSheets().some(s=>s.getLastColumn()>200||s.getLastRow()>MDM.maxRows+1000))fail_('Máximo 200 columnas y 50.000 filas de datos por hoja.');
    const job=newRow_({owner_id:p.owner_id,owner_type:p.type,original_name:name,sha256:hash,source_file_id:source.getId(),converted_file_id:convertedId,staging_file_id:'',status:'uploaded',mapping:'',cursor:0,summary:'',settings:'',price_list_id:'',expires_at:new Date(Date.now()+24*3600000).toISOString()},email);
    append_('ImportJobs',job);
    return {job:job,sheets:book.getSheets().map(s=>({name:s.getName(),rows:s.getLastRow(),columns:s.getLastColumn()})),alreadyImported:rows_('PriceLists').filter(r=>r.owner_id===p.owner_id&&r.source_file_sha256===hash).map(r=>r.revision),templates:rows_('MappingTemplates').filter(r=>r.owner_id===p.owner_id&&active_(r.active))};
  } catch(e) { if(convertedId)DriveApp.getFileById(convertedId).setTrashed(true);if(source)source.setTrashed(true);throw e; }
}
function sourceSheet_(j,sheet) { const book=SpreadsheetApp.openById(j.converted_file_id),s=book.getSheetByName(sheet);if(!s)fail_('Selecciona una hoja válida.');return s; }
function suggestMapping_(sheet,headers,headerRow,start) {
  const norm=v=>cellText_(v).toLowerCase().replace(/\s+/g,' '),names=headers.map(norm);
  const fields={},prices=[],dimensions=[];
  const add=(field,col)=>{fields[field]={col:col,header:cellText_(headers[col])};};
  const price=(col,type,ccy,ccyCol)=>prices.push({col:col,header:cellText_(headers[col]),price_type:type,currency:ccyCol==null?{mode:'fixed',value:ccy}:{mode:'column',col:ccyCol,header:cellText_(headers[ccyCol])}});
  if(sheet==='ALL'&&names[7]==='ean'&&names[0]==='asin') {
    Object.entries({asin:0,ean:7,upc:8,brand:10,description:11,moq:19,case_pack_qty:20}).forEach(([k,c])=>add(k,c));
    [1,6].forEach(c=>dimensions.push({col:c,header:cellText_(headers[c])}));price(17,'domestic_cost','USD');price(18,'import_cost','USD');price(23,'rrp',null,22);
  } else if(['ean','barcode'].includes(names[1])&&names[11]&&names[11].includes('price')) {
    Object.entries({ean:1,asin:2,vendor_sku:3,description:8,hs_code:28,country_of_origin:30,case_pack_qty:32}).forEach(([k,c])=>add(k,c));
    price(11,'purchase','EUR');price(13,'rrp','EUR');price(20,'rrp_ex_vat','MXN');price(21,'rrp','MXN');price(22,'retailer_cost','MXN');price(23,'retailer_cost','USD');
  } else {
    const aliases={ean:['ean','barcode','gtin'],upc:['upc'],asin:['asin'],vendor_sku:['vendor sku','article','item no.','item no'],description:['description','item name'],brand:['brand','brand name'],category:['category'],moq:['moq'],case_pack_qty:['case pack quantity','case pack'],country_of_origin:['country of origin'],hs_code:['customs','hs code']};
    Object.entries(aliases).forEach(([k,vals])=>{const c=names.findIndex(n=>vals.includes(n));if(c>=0)add(k,c);});
    names.forEach((h,c)=>{if(!h||h.includes('margin')||h.includes('currency'))return;let type=h.includes('domestic cost')?'domestic_cost':h.includes('import cost')?'import_cost':h.includes('retailer')?'retailer_cost':h.includes('no vat')||h.includes('ex vat')?'rrp_ex_vat':h.includes('rrp')||h.includes('rsp')||h.includes('retail price')?'rrp':h.includes('price')?'purchase':null;if(type){const m=h.match(/\b(usd|eur|mxn|gbp)\b/);price(c,type,m?m[1].toUpperCase():h.includes('€')?'EUR':'');}});
  }
  return {sheet:sheet,header_row:headerRow,data_start_row:start,fields:fields,dimensions:dimensions,prices:prices,expected_headers:headers.map(cellText_)};
}
function previewImport_(p,email) {
  const j=importJob_(p.id,email);if(j.status!=='uploaded')fail_('La importación ya está en validación.');
  const s=sourceSheet_(j,p.sheet),width=s.getLastColumn();if(!width||!s.getLastRow())fail_('La hoja está vacía.');
  const top=s.getRange(1,1,Math.min(s.getLastRow(),30),width).getValues();
  let header=Number(p.header_row)||0;
  if(!header) {
    let best=-1;top.forEach((r,i)=>{const score=r.reduce((n,v)=>n+(/^(ean|asin|barcode|item name|description|price|brand|upc|customs)/i.test(cellText_(v))?1:0),0);if(score>best){best=score;header=i+1;}});
  }
  header=integer_(header,1,Math.min(1000,s.getLastRow()),'header_row');
  const headers=s.getRange(header,1,1,width).getValues()[0];
  const knownAmazon=p.sheet==='ALL'&&cellText_(headers[7]).toLowerCase()==='ean';
  const start=integer_(p.data_start_row||header+(knownAmazon?3:1),header+1,1001,'data_start_row');
  const remaining=Math.max(0,Math.min(20,s.getLastRow()-start+1));
  const metadata=s.getRange(1,1,Math.max(1,header-1),width).getValues().map(r=>r.map(cellText_));
  const match=JSON.stringify(metadata).match(/(?:valid from|gültig ab)[^\d]*(\d{2})\.(\d{2})\.(\d{4})/i);
  return {headers:headers.map(cellText_),rows:remaining?s.getRange(start,1,remaining,width).getValues():[],metadata:metadata,header_row:header,data_start_row:start,suggestedValidFrom:match?match[3]+'-'+match[2]+'-'+match[1]:'',mapping:suggestMapping_(p.sheet,headers,header,start)};
}
function mapping_(raw,j) {
  if(!raw||typeof raw!=='object')fail_('Falta el mapeo.');
  const s=sourceSheet_(j,raw.sheet),width=s.getLastColumn();
  const header=integer_(raw.header_row,1,1000,'header_row'),start=integer_(raw.data_start_row,header+1,1001,'data_start_row');
  const headers=s.getRange(header,1,1,width).getValues()[0].map(cellText_);
  if(raw.expected_headers&&JSON.stringify(raw.expected_headers)!==JSON.stringify(headers))fail_('El archivo cambió de estructura. Revisa el mapeo.');
  const ref=r=>{const col=column_(r.col);if(col>=width)fail_('Columna fuera de la hoja.');if(r.header!=null&&cellText_(r.header)!==headers[col])fail_('La cabecera de '+letter_(col)+' cambió. Revisa la plantilla.');return {col:col,header:headers[col]};};
  const allowed=['ean','upc','asin','vendor_sku','description','brand','category','case_pack_qty','moq','uom','country_of_origin','hs_code'],fields={};
  Object.keys(raw.fields||{}).forEach(k=>{if(!allowed.includes(k))fail_('Campo de producto no válido.');fields[k]=ref(raw.fields[k]);});
  if(!['ean','upc','asin'].some(k=>fields[k]))fail_('Mapea EAN, UPC o ASIN.');
  if(!Array.isArray(raw.prices)||!raw.prices.length||raw.prices.length>30)fail_('Mapea entre 1 y 30 precios.');
  const types=lookup_('price_type').map(r=>r.code),seen={};
  const prices=raw.prices.map(p=>{
    const out=Object.assign(ref(p),{price_type:enum_(p.price_type,types,'price_type')});
    if(!p.currency)fail_('Cada precio necesita su moneda.');
    out.currency=p.currency.mode==='column'?Object.assign({mode:'column'},ref(p.currency)):{mode:'fixed',value:lookupCode_('currency',p.currency.value,true,'currency')};
    const key=JSON.stringify([out.price_type,out.currency.mode,out.currency.value,out.currency.col]);if(seen[key])fail_('Un tipo de precio y moneda está repetido.');seen[key]=true;return out;
  });
  if((raw.dimensions||[]).length>10)fail_('Máximo 10 dimensiones.');
  if(s.getLastRow()-start+1>MDM.maxRows)fail_('Máximo 50.000 filas.');
  return {sheet:raw.sheet,header_row:header,data_start_row:start,fields:fields,dimensions:(raw.dimensions||[]).map(ref),prices:prices,expected_headers:headers};
}
function priceColumns_(mapping) { return mapping.prices.map((p,i)=>({index:i,price_type:p.price_type,currency_mode:p.currency.mode,currency:p.currency.value||'',source_column:letter_(p.col),amount_field:'p'+i+'_amount',currency_field:'p'+i+'_currency'})); }
function lineHeaders_(mapping) { return LINE_BASE.concat(mapping.prices.flatMap((_,i)=>['p'+i+'_amount','p'+i+'_currency'])); }
function processRow_(values,number,mapping,lookups,id,email) {
  if(values.every(empty_))return {empty:true};
  const data={source_row:number},issues=[],warn=c=>{if(!issues.includes(c))issues.push(c);};
  const cell=col=>values[col],get=k=>mapping.fields[k]?cell(mapping.fields[k].col):'';
  ['ean','upc','asin'].forEach(k=>{data[k]=productCode_(get(k));if(data[k]&&!(k==='asin'?asin_(data[k]):gtin_(data[k])))warn('invalid_'+k);});
  if(!data.ean&&!data.upc&&!data.asin)return {rejected:true,issues:['no_product_key'],source_row:number};
  const limits={vendor_sku:100,description:1000,brand:100,category:100,uom:20,hs_code:20};
  Object.keys(limits).forEach(k=>{let v=k==='hs_code'?productCode_(get(k)):cellText_(get(k));if(v.length>limits[k]){warn('too_long_'+k);v=v.slice(0,limits[k]);}data[k]=v;});
  ['case_pack_qty','moq'].forEach(k=>{try{data[k]=empty_(get(k))?'':integer_(get(k),0,2147483647,k);}catch(e){data[k]='';warn('invalid_'+k);}});
  data.country_of_origin=cellText_(get('country_of_origin')).toUpperCase();if(data.country_of_origin&&!lookups.countries.includes(data.country_of_origin)){warn('invalid_country');data.country_of_origin='';}
  const dims={};mapping.dimensions.forEach(d=>dims[letter_(d.col)]=cellText_(cell(d.col)));data.dimensions=JSON.stringify(dims);
  data.dup_key=sha_(JSON.stringify([data.ean,data.upc,data.asin,Object.entries(dims).sort()]));
  const priceCounts={};mapping.prices.forEach((p,i)=>{
    let amount;try{amount=money_(cell(p.col));}catch(e){warn('invalid_amount');return;}
    if(!amount)return;if(amount.startsWith('-')){warn('negative_amount');return;}
    const currency=p.currency.mode==='fixed'?p.currency.value:cellText_(cell(p.currency.col)).toUpperCase();
    if(!currency){warn('missing_currency');return;}if(!lookups.currencies.includes(currency)){warn('invalid_currency');return;}
    data['p'+i+'_amount']=amount;data['p'+i+'_currency']=currency;const key=p.price_type+'|'+currency;priceCounts[key]=(priceCounts[key]||0)+1;
  });
  const raw={};values.forEach((v,i)=>{if(!empty_(v))raw[letter_(i)]=v;});data.raw_row=JSON.stringify(raw);textCell_(data.raw_row);
  data.issues=JSON.stringify(issues);
  const row=newRow_(data,email),hash=sha_('line:'+id+':'+number).slice(0,32).split('');
  hash[12]='5';hash[16]=((parseInt(hash[16],16)&3)|8).toString(16);
  const stable=hash.join('');row.id=[stable.slice(0,8),stable.slice(8,12),stable.slice(12,16),stable.slice(16,20),stable.slice(20)].join('-');
  return {line:row,issues:issues,priceCounts:priceCounts};
}
function startValidation_(p,email) {
  const j=importJob_(p.id,email);party_(j.owner_type,j.owner_id,true);
  if(j.status!=='uploaded')fail_('Ya se inició la validación.');if(p.confirmed!==true)fail_('Confirma los precios y sus monedas.');
  const mapping=mapping_(p.mapping,j),book=SpreadsheetApp.create('Validación '+j.id);initSheet_(book,'Lines',lineHeaders_(mapping));
  book.getSheets().filter(s=>s.getName()!=='Lines').forEach(s=>book.deleteSheet(s));DriveApp.getFileById(book.getId()).moveTo(folder_('MDM_STAGING_FOLDER_ID'));
  const summary={rows_read:0,lines:0,lines_with_warnings:0,rows_rejected:0,prices_total:0,prices:{},issue_counts:{},examples:[],duplicate_groups:0};
  const updated=changed_(j,{status:'validating',staging_file_id:book.getId(),mapping:JSON.stringify(mapping),cursor:mapping.data_start_row,summary:JSON.stringify(summary)},email);replace_('ImportJobs',updated);
  return jobProgress_(updated);
}
function jobProgress_(j) { return {id:j.id,status:j.status,cursor:Number(j.cursor),summary:json_(j.summary,{}),price_list_id:j.price_list_id}; }
function validateChunk_(p,email) {
  const j=importJob_(p.id,email);
  if(j.status==='validated'||j.status==='committed')return jobProgress_(j);
  if(j.status!=='validating')fail_('Primero confirma el mapeo.');
  if(Number(p.cursor)!==Number(j.cursor))return jobProgress_(j); // harmless replay after a lost response
  const mapping=json_(j.mapping,{}),sheet=sourceSheet_(j,mapping.sheet),summary=json_(j.summary,{}),cursor=Number(j.cursor);
  const count=Math.max(0,Math.min(MDM.batchSize,sheet.getLastRow()-cursor+1));
  const input=count?sheet.getRange(cursor,1,count,sheet.getLastColumn()).getValues():[],lines=[];
  const lookups={currencies:lookup_('currency').map(r=>r.code),countries:lookup_('country').map(r=>r.code)};
  input.forEach((r,i)=>{
    const result=processRow_(r,cursor+i,mapping,lookups,j.id,email);if(result.empty)return;summary.rows_read++;
    if(result.rejected)summary.rows_rejected++;
    else{lines.push(result.line);if(result.issues.length)summary.lines_with_warnings++;Object.entries(result.priceCounts).forEach(([k,n])=>{summary.prices[k]=(summary.prices[k]||0)+n;summary.prices_total+=n;});}
    result.issues.forEach(code=>{summary.issue_counts[code]=(summary.issue_counts[code]||0)+1;if(summary.examples.length<50)summary.examples.push({row:cursor+i,code:code});});
  });
  const target=SpreadsheetApp.openById(j.staging_file_id).getSheetByName('Lines'),headers=lineHeaders_(mapping);
  if(lines.length){const end=summary.lines+lines.length+1;if(end>target.getMaxRows())target.insertRowsAfter(target.getMaxRows(),end-target.getMaxRows());target.getRange(summary.lines+2,1,lines.length,headers.length).setNumberFormat('@').setValues(lines.map(r=>headers.map(h=>textCell_(r[h]))));}
  summary.lines+=lines.length;const done=cursor+count>sheet.getLastRow();
  if(done){const dup=duplicateMap_(readSheet_(target));summary.duplicate_groups=Object.values(dup).filter(n=>n>1).length;summary.lines_ok=summary.lines-summary.lines_with_warnings;}
  const updated=changed_(j,{cursor:cursor+count,status:done?'validated':'validating',summary:JSON.stringify(summary)},email);replace_('ImportJobs',updated);return jobProgress_(updated);
}
function commitImport_(p,email) {
  const j=importJob_(p.id,email);party_(j.owner_type,j.owner_id,true);
  if(j.status==='committed')return get_('PriceLists',j.price_list_id);
  if(j.status!=='validated')fail_('Espera a que termine la validación.');
  const existing=rows_('PriceLists').find(r=>r.id===j.id);if(existing){replace_('ImportJobs',changed_(j,{status:'committed',price_list_id:existing.id},email));return existing;}
  const summary=json_(j.summary,{});if(!summary.lines)fail_('No hay líneas válidas para importar.');
  const name=str_(p.name,200,true,'name'),currency=lookupCode_('currency',p.currency,true,'currency'),from=date_(p.valid_from,true,'valid_from'),to=date_(p.valid_to,false,'valid_to'),notes=str_(p.notes,1000,false,'notes');
  if(to&&to<from)fail_('La fecha final debe ser igual o posterior a la inicial.','valid_to');
  const templateName=str_(p.template_name,100,false,'template_name'),mapping=json_(j.mapping,{}),source=sourceSheet_(j,mapping.sheet);
  const metadata={rows_above_header:source.getRange(1,1,Math.max(1,mapping.header_row-1),source.getLastColumn()).getValues(),summary:summary,cached_formula_values:true};
  textCell_(metadata);
  const previous=rows_('PriceLists').filter(r=>r.owner_id===j.owner_id&&r.owner_type===j.owner_type).sort((a,b)=>Number(b.revision)-Number(a.revision));
  const row=newRow_({owner_id:j.owner_id,owner_type:j.owner_type,name:name,currency:currency,valid_from:from,valid_to:to,status:'draft',revision:previous.length?Number(previous[0].revision)+1:1,supersedes_id:previous.length?previous[0].id:'',source_file_name:j.original_name,source_file_id:j.source_file_id,source_file_sha256:j.sha256,source_sheet:mapping.sheet,imported_at:now_(),imported_by:email,line_count:summary.lines,metadata:JSON.stringify(metadata),lines_file_id:j.staging_file_id,price_columns:JSON.stringify(priceColumns_(mapping)),notes:notes},email);row.id=j.id;
  DriveApp.getFileById(j.staging_file_id).setName('PL_'+row.revision+'_'+name).moveTo(folder_('MDM_LISTS_FOLDER_ID'));
  persist_('PriceLists',null,row,email,'import');
  if(templateName)persist_('MappingTemplates',null,newRow_({owner_id:j.owner_id,owner_type:j.owner_type,name:templateName,mapping:JSON.stringify(mapping),header_fingerprint:sha_(JSON.stringify(mapping.expected_headers))},email),email,'save_mapping');
  replace_('ImportJobs',changed_(j,{status:'committed',price_list_id:row.id},email));
  if(j.converted_file_id)DriveApp.getFileById(j.converted_file_id).setTrashed(true);return row;
}
function cancelImport_(p,email) {
  const j=importJob_(p.id,email);if(j.status==='committed')fail_('La importación ya se guardó.');
  [j.converted_file_id,j.staging_file_id,j.source_file_id].filter(Boolean).forEach(id=>DriveApp.getFileById(id).setTrashed(true));
  replace_('ImportJobs',changed_(j,{status:'cancelled'},email));return {cancelled:true};
}
