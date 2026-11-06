/** Pure tests: no business rows are created or deleted. */
function runTests() {
  ownerOnly_();let count=0;
  const equal=(actual,expected,label)=>{if(JSON.stringify(actual)!==JSON.stringify(expected))throw new Error(label+': '+JSON.stringify(actual)+' != '+JSON.stringify(expected));count++;};
  equal(gtin_('4033766024122'),true,'GTIN válido');equal(gtin_('043917996264'),true,'UPC con cero');equal(gtin_('43917996264'),false,'No corregir un cero perdido');equal(productCode_('00012345.0'),'00012345','Conservar ceros');
  equal(productCode_('#N/A'),'','Error Excel vacío');equal(productCode_(' '),'','Espacios vacíos');equal(asin_('B003QQ37HI'),true,'ASIN');equal(asin_('1234567890'),true,'ASIN numérico');equal(asin_('bad'),false,'ASIN inválido');
  equal(money_('78.11261999999999'),'78.1126','Cuatro decimales');equal(money_('1.234,56789 EUR'),'1234.5679','Separadores');equal(money_('0'),'0.0000','Cero');equal(money_('99999999999999.9999'),'99999999999999.9999','18 dígitos exactos');equal(money_('1.99995'),'2.0000','Acarreo');equal(money_('1e-7'),'0.0000','Notación científica');
  equal(textCell_('=IMPORTXML("x")'),"'=IMPORTXML(\"x\")",'Fórmula como texto');equal(textCell_('+123'),"'+123",'Prefijo seguro');
  const mappings={sheet:'CSV',header_row:1,data_start_row:2,fields:{ean:{col:0},asin:{col:1},description:{col:2}},dimensions:[],prices:[{col:3,price_type:'purchase',currency:{mode:'fixed',value:'EUR'}}]};
  const lookups={currencies:['EUR','USD','MXN'],countries:['DE','MX']};
  const result=processRow_(['4033766024122.0',' ','Product','1.23455'],2,mappings,lookups,'test','test@buenavidatrading.com');
  equal(result.line.ean,'4033766024122','Normalización');equal(result.line.asin,'','ASIN vacío');equal(result.line.p0_amount,'1.2346','Precio exacto');equal(result.line.p0_currency,'EUR','Moneda');equal(result.issues,[],'Sin avisos');
  equal(processRow_(['','','Product','1'],3,mappings,lookups,'test','test').rejected,true,'Sin clave');
  const second=processRow_(['4033766024122','','Other','2'],4,mappings,lookups,'test','test');equal(result.line.dup_key,second.line.dup_key,'Duplicado sin dimensiones');
  mappings.dimensions=[{col:2}];const third=processRow_(['4033766024122','','Port A','2'],5,mappings,lookups,'test','test');equal(result.line.dup_key===third.line.dup_key,false,'Dimensión distingue');
  equal(Object.values(duplicateMap_([result.line,second.line])).filter(n=>n>1).length,1,'Detectar duplicados');second.line.active=false;equal(Object.values(duplicateMap_([result.line,second.line])).filter(n=>n>1).length,0,'Exclusión resuelve');
  console.log('OK: '+count+' comprobaciones puras.');return {passed:count};
}
/** Optional: IDs of original sample XLSX files in Script Properties (owner uploads them).
 * Tests sanitizer + actual Google conversion + same parser; temporary files go to trash.
 * No Companies/Customers/Vendors/PriceLists are created.
 */
function runSampleTests() {
  const email=ownerOnly_(),results=[];
  [['MDM_TEST_AMAZON_ID','ALL',4,7,7515,15030],['MDM_TEST_NOBBY_ID','Tabelle1',7,8,7515,45061]].forEach(spec=>{
    const id=props_().getProperty(spec[0]);if(!id)throw new Error('Falta Script Property '+spec[0]);
    let converted;
    try{
      converted=Drive.Files.create({name:'MDM sample verification',mimeType:'application/vnd.google-apps.spreadsheet',parents:[props_().getProperty('MDM_STAGING_FOLDER_ID')]},safeXlsx_(DriveApp.getFileById(id).getBlob()),{fields:'id'});
      const s=SpreadsheetApp.openById(converted.id).getSheetByName(spec[1]),values=s.getDataRange().getValues(),mapping=suggestMapping_(spec[1],values[spec[2]-1],spec[2],spec[3]);
      const lookups={currencies:lookup_('currency').map(r=>r.code),countries:lookup_('country').map(r=>r.code)},lines=[],prices={},issues={};let emptyAsin=0;
      values.slice(spec[3]-1).forEach((r,i)=>{const parsed=processRow_(r,i+spec[3],mapping,lookups,'test',email);if(parsed.empty)return;if(parsed.rejected)throw new Error('Fila rechazada '+(i+spec[3]));lines.push(parsed.line);if(!parsed.line.asin)emptyAsin++;parsed.issues.forEach(k=>issues[k]=(issues[k]||0)+1);Object.entries(parsed.priceCounts).forEach(([k,n])=>prices[k]=(prices[k]||0)+n);});
      const total=Object.values(prices).reduce((a,b)=>a+b,0);
      if(lines.length!==spec[4]||total!==spec[5]||emptyAsin!==1970||JSON.stringify(issues)!==JSON.stringify({invalid_ean:1}))throw new Error('No coincide '+spec[0]+': '+JSON.stringify({lines:lines.length,prices:total,emptyAsin:emptyAsin,issues:issues}));
      results.push({sample:spec[0],lines:lines.length,prices:prices,issues:issues,emptyAsin:emptyAsin});
    }finally{if(converted)DriveApp.getFileById(converted.id).setTrashed(true);}
  });
  console.log(JSON.stringify(results));return results;
}
