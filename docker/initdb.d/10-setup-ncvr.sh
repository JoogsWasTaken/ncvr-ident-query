#!/bin/bash
set -eux

cd /tmp
curl -o ncvr.zip -sL "https://s3.amazonaws.com/dl.ncsbe.gov/data/ncvoter_Statewide.zip"
unzip -q ncvr.zip
mv ./*.txt ncvr.txt

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE ncvr (
    county_id int,
    county_desc varchar(15),
    voter_reg_num char(12),
    ncid char(12),
    last_name varchar(25),
    first_name varchar(20),
    middle_name varchar(20),
    name_suffix_lbl char(4),
    status_cd char(2),
    voter_status_desc varchar(25),
    reason_cd char(2),
    voter_status_reason_desc varchar(60),
    res_street_address varchar(65),
    res_city_desc varchar(60),
    state_cd varchar(2),
    zip_code char(9),
    mail_addr1 varchar(40),
    mail_addr2 varchar(40),
    mail_addr3 varchar(40),
    mail_addr4 varchar(40),
    mail_city varchar(30),
    mail_state varchar(2),
    mail_zipcode char(9),
    full_phone_number varchar(12),
    confidential_ind char(1),
    registr_dt date,
    race_code char(3),
    ethnic_code char(3),
    party_cd char(3),
    gender_code char(1),
    birth_year int,
    age_at_year_end int,
    birth_state varchar(2),
    drivers_lic char(1),
    precinct_abbrv varchar(6),
    precinct_desc varchar(60),
    municipality_abbrv varchar(6),
    municipality_desc varchar(60),
    ward_abbrv varchar(6),
    ward_desc varchar(60),
    cong_dist_abbrv varchar(6),
    super_court_abbrv varchar(6),
    judic_dist_abbrv varchar(6),
    nc_senate_abbrv varchar(6),
    nc_house_abbrv varchar(6),
    county_commiss_abbrv varchar(6),
    county_commiss_desc varchar(60),
    township_abbrv varchar(6),
    township_desc varchar(60),
    school_dist_abbrv varchar(6),
    school_dist_desc varchar(60),
    fire_dist_abbrv varchar(6),
    fire_dist_desc varchar(60),
    water_dist_abbrv varchar(6),
    water_dist_desc varchar(60),
    sewer_dist_abbrv varchar(6),
    sewer_dist_desc varchar(60),
    sanit_dist_abbrv varchar(6),
    sanit_disc_desc varchar(60),
    rescue_dist_abbrv varchar(6),
    rescue_dist_desc varchar(60),
    munic_dist_abbrv varchar(6),
    munic_dist_desc varchar(60),
    dist_1_abbrv varchar(6),
    dist_1_desc varchar(60),
    vtd_abbrv varchar(6),
    vtd_desc varchar(60)
);

\copy ncvr FROM '/tmp/ncvr.txt' CSV DELIMITER E'\t' NULL '' HEADER QUOTE '"' ENCODING 'LATIN1';

ALTER TABLE ncvr ADD CONSTRAINT pk_ncvr PRIMARY KEY (ncid);

CREATE MATERIALIZED VIEW ncvr_plausible AS
SELECT county_desc AS county, ncid, last_name, first_name, middle_name, name_suffix_lbl AS name_suffix, reason_cd, res_street_address AS res_street, res_city_desc AS res_city, state_cd AS res_state_cd, zip_code AS res_zip, mail_addr1 AS mail_street, mail_city, mail_state AS mail_state_cd, mail_zipcode AS mail_zip, full_phone_number, confidential_ind, registr_dt, race_code AS race_cd, ethnic_code AS ethnic_cd, party_cd, gender_code AS gender_cd, birth_year, age_at_year_end, birth_state AS birth_state_cd, drivers_lic AS drivers_lic_ind FROM ncvr
WHERE confidential_ind = 'N'
AND reason_cd = 'AV'
AND EXTRACT(YEAR FROM registr_dt) >= birth_year + 16
AND age_at_year_end <= 120
AND zip_code <> '00000'
AND mail_zipcode <> '00000'
AND full_phone_number !~ '^0+$'
AND LENGTH(mail_zipcode) in (5, 9);
EOSQL

rm /tmp/*