/** BVT MDM · V8 · No build step. Private functions end in _. */
const MDM = Object.freeze({domain:'buenavidatrading.com', pageSize:50, batchSize:400, maxBytes:20*1024*1024, maxRows:50000});
const COMMON = ['id','created_at','created_by','updated_at','updated_by','active','version'];
const SCHEMA = Object.freeze({
  Companies: COMMON.concat(['code','legal_name','trade_name','eori','country_code','tax_registration_number','is_default']),
  Customers: COMMON.concat(['code','legal_name','trade_name','country_code','status','default_currency','payment_term_code','incoterm_code']),
  Vendors: COMMON.concat(['code','legal_name','trade_name','eori','country_code','status','default_currency','payment_term_code','incoterm_code','lead_time_days','moq']),
  Addresses: COMMON.concat(['owner_id','owner_type','address_type','line1','line2','postal_code','city','region','country_code']),
  Contacts: COMMON.concat(['owner_id','owner_type','name','role_title','contact_role','email','phone','is_primary']),
  VendorCodes: COMMON.concat(['owner_id','owner_type','parent_code','child_code','destination_country']),
  PriceLists: COMMON.concat(['owner_id','owner_type','name','currency','valid_from','valid_to','status','revision','supersedes_id','source_file_name','source_file_id','source_file_sha256','source_sheet','imported_at','imported_by','line_count','metadata','lines_file_id','price_columns','notes']),
  MappingTemplates: COMMON.concat(['owner_id','owner_type','name','mapping','header_fingerprint']),
  AuditLog: ['id','timestamp','user_email','action','entity','entity_id','old_values','new_values'],
  Lookups: ['kind','code','name','days','minor_units','sort_order'],
  ImportJobs: COMMON.concat(['owner_id','owner_type','original_name','sha256','source_file_id','converted_file_id','staging_file_id','status','mapping','cursor','summary','settings','price_list_id','expires_at'])
});
const LINE_BASE = COMMON.concat(['source_row','ean','upc','asin','vendor_sku','description','brand','category','case_pack_qty','moq','uom','country_of_origin','hs_code','dimensions','dup_key','issues','raw_row']);
const OWNER_TABLE = {company:'Companies',customer:'Customers',vendor:'Vendors'};
const FIELD_LIMITS = {code:20,legal_name:200,trade_name:200,eori:17,country_code:2,tax_registration_number:50,status:20,default_currency:3,payment_term_code:20,incoterm_code:3,line1:200,line2:200,postal_code:20,city:100,region:100,address_type:20,name:200,role_title:100,contact_role:20,email:254,phone:40,parent_code:20,child_code:20,destination_country:2};
