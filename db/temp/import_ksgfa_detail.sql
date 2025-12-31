-- Import KGFA detail CSV data
-- CSV column order: company,contact,phone,street,city,state,zip,website,notes,detail_url
COPY ksgfa_detail(company, contact, phone, street, city, state, zip, website, notes, detail_url) 
FROM '/tmp/aginfo-import/ksgfa_detail.csv' 
WITH (FORMAT csv, HEADER true, DELIMITER ',', QUOTE '"', ESCAPE '"');
