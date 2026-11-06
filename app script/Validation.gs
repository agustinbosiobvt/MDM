function str_(v,max,required,field) {
  if(v!=null && !['string','number'].includes(typeof v)) fail_('Valor inválido.',field);
  const s=v==null?'':String(v).trim();
  if(required&&!s) fail_('Este campo es obligatorio.',field);
  if(s.length>max) fail_('Máximo '+max+' caracteres.',field); return s;
}
function enum_(v,values,field) { if(!values.includes(v)) fail_('Selecciona un valor válido.',field); return v; }
function lookupCode_(kind,value,required,field) {
  const code=str_(value,40,required,field).toUpperCase();
  if(code&&!lookup_(kind).some(r=>r.code===code)) fail_('Código no válido.',field); return code;
}
function integer_(value,min,max,field) {
  if(value===''||value==null) return '';
  const v=Number(value); if(!Number.isSafeInteger(v)||v<min||v>max) fail_('Introduce un entero entre '+min+' y '+max+'.',field); return v;
}
function date_(value,required,field) {
  const s=str_(value,10,required,field); if(!s)return '';
  if(!/^\d{4}-\d{2}-\d{2}$/.test(s)||!Number.isFinite(Date.parse(s))||new Date(s).toISOString().slice(0,10)!==s) fail_('Fecha no válida.',field); return s;
}
function empty_(v) { return v==null || (typeof v==='string' && (!v.trim() || /^#(?:N\/A!?|NA|VALUE!|REF!|DIV\/0!|NUM!|NAME\?|NULL!|SPILL!)$/i.test(v.trim()))); }
function cellText_(v) { if(empty_(v))return ''; return String(v).trim().replace(/^(\d+)\.0+$/,'$1'); }
function productCode_(v) { return cellText_(v).replace(/\s/g,''); }
function gtin_(s) {
  if(!/^\d{8}$|^\d{12,14}$/.test(s))return false;
  let sum=0; const body=s.slice(0,-1).split('').reverse(); body.forEach((v,i)=>sum+=Number(v)*(i%2?1:3));
  return (10-sum%10)%10===Number(s.slice(-1));
}
function asin_(s) { return /^[A-Z0-9]{10}$/.test(s); }
/** Decimal string arithmetic. Never use floating point to round money. */
function money_(value) {
  if(empty_(value))return '';
  if(typeof value==='boolean')throw new Error('Importe inválido');
  let s=String(value).trim().replace(/EUR|USD|MXN|[\s€$£¥]/gi,'');
  if(s.includes(',')&&s.includes('.')) s=s.lastIndexOf(',')>s.lastIndexOf('.')?s.replace(/\./g,'').replace(',','.'):s.replace(/,/g,'');
  else if(s.includes(','))s=s.replace(',','.');
  const scientific=s.match(/^([+-]?)(\d+)(?:\.(\d*))?[eE]([+-]?\d+)$/);
  if(scientific) {
    const digits=scientific[2]+(scientific[3]||''), point=scientific[2].length+Number(scientific[4]);
    if(Math.abs(point)>100)throw new Error('Importe fuera de rango');
    s=scientific[1]+(point<=0?'0.'+'0'.repeat(-point)+digits:point>=digits.length?digits+'0'.repeat(point-digits.length):digits.slice(0,point)+'.'+digits.slice(point));
  }
  const m=s.match(/^([+-]?)(\d*)(?:\.(\d*))?$/); if(!m||!(m[2]||m[3]))throw new Error('Importe inválido');
  let whole=(m[2]||'0').replace(/^0+(?=\d)/,''), frac=(m[3]||'').padEnd(5,'0');
  let digits=whole+frac.slice(0,4);
  if(Number(frac[4])>=5) {
    const a=digits.split(''); let carry=1;
    for(let i=a.length-1;i>=0&&carry;i--){const n=Number(a[i])+carry;a[i]=String(n%10);carry=n>9?1:0;}
    if(carry)a.unshift('1');digits=a.join('');
  }
  digits=digits.padStart(5,'0');whole=digits.slice(0,-4).replace(/^0+(?=\d)/,'');
  if(whole.length>14)throw new Error('Importe fuera de NUMERIC(18,4)');
  return (m[1]==='-'&&!/^0+$/.test(digits)?'-':'')+whole+'.'+digits.slice(-4);
}
function sha_(value) {
  const bytes=typeof value==='string'?Utilities.newBlob(value).getBytes():value;
  return Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256,bytes).map(n=>(n<0?n+256:n).toString(16).padStart(2,'0')).join('');
}
