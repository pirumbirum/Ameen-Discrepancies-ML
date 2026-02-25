# Federal Court Identifiers on CourtListener

CourtListener has 3,355+ jurisdictions. Each court has a unique string ID used for API filtering. This document covers all federal courts relevant to PACER data.

> **Full list:** https://www.courtlistener.com/help/api/jurisdictions/
> **Courts-DB repo:** https://github.com/freelawproject/courts-db

---

## Court Object Structure

```json
{
    "resource_uri": "https://www.courtlistener.com/api/rest/v4/courts/nysd/",
    "id": "nysd",
    "full_name": "United States District Court for the Southern District of New York",
    "short_name": "S.D.N.Y.",
    "jurisdiction": "FD",
    "in_use": true,
    "has_opinion_scraper": true,
    "has_oral_argument_scraper": false,
    "position": 2.52,
    "citation_string": "S.D.N.Y.",
    "date_modified": "2024-01-15T10:30:00Z",
    "url": "https://www.nysd.uscourts.gov/",
    "start_date": "1789-09-24",
    "end_date": null
}
```

---

## Court Jurisdiction Types

| Code | Jurisdiction Type | Description |
|------|-------------------|-------------|
| `F` | Federal Appellate | Circuit Courts of Appeals |
| `FD` | Federal District | U.S. District Courts |
| `FB` | Federal Bankruptcy | Bankruptcy Courts |
| `FBP` | Federal Bankruptcy Panel | Bankruptcy Appellate Panels |
| `FS` | Federal Special | Specialized Federal Courts |
| `S` | State | State Supreme Courts |
| `SA` | State Appellate | State Appellate Courts |
| `ST` | State Trial | State Trial Courts |
| `SS` | State Special | Specialized State Courts |
| `SAG` | State Attorney General | State AG Opinions |
| `C` | Committee | Committees |
| `T` | Tribal | Tribal Courts |
| `I` | International | International Courts |
| `testing` | Testing | Test courts |

### Filter by Jurisdiction Type
```
GET /api/rest/v4/dockets/?court__jurisdiction=FD    # All federal district courts
GET /api/rest/v4/dockets/?court__jurisdiction=FB    # All bankruptcy courts
```

---

## Supreme Court

| Court ID | Full Name |
|----------|-----------|
| `scotus` | Supreme Court of the United States |

---

## Circuit Courts of Appeals (Federal Appellate - `F`)

| Court ID | Full Name |
|----------|-----------|
| `ca1` | U.S. Court of Appeals for the First Circuit |
| `ca2` | U.S. Court of Appeals for the Second Circuit |
| `ca3` | U.S. Court of Appeals for the Third Circuit |
| `ca4` | U.S. Court of Appeals for the Fourth Circuit |
| `ca5` | U.S. Court of Appeals for the Fifth Circuit |
| `ca6` | U.S. Court of Appeals for the Sixth Circuit |
| `ca7` | U.S. Court of Appeals for the Seventh Circuit |
| `ca8` | U.S. Court of Appeals for the Eighth Circuit |
| `ca9` | U.S. Court of Appeals for the Ninth Circuit |
| `ca10` | U.S. Court of Appeals for the Tenth Circuit |
| `ca11` | U.S. Court of Appeals for the Eleventh Circuit |
| `cadc` | U.S. Court of Appeals for the D.C. Circuit |
| `cafc` | U.S. Court of Appeals for the Federal Circuit |

---

## Federal District Courts (Federal District - `FD`)

### First Circuit
| Court ID | Full Name |
|----------|-----------|
| `mad` | District of Massachusetts |
| `med` | District of Maine |
| `nhd` | District of New Hampshire |
| `rid` | District of Rhode Island |
| `prd` | District of Puerto Rico |

### Second Circuit
| Court ID | Full Name |
|----------|-----------|
| `nyed` | Eastern District of New York |
| `nynd` | Northern District of New York |
| `nysd` | Southern District of New York |
| `nywd` | Western District of New York |
| `ctd` | District of Connecticut |
| `vtd` | District of Vermont |

### Third Circuit
| Court ID | Full Name |
|----------|-----------|
| `ded` | District of Delaware |
| `njd` | District of New Jersey |
| `paed` | Eastern District of Pennsylvania |
| `pamd` | Middle District of Pennsylvania |
| `pawd` | Western District of Pennsylvania |
| `vid` | District of the Virgin Islands |

### Fourth Circuit
| Court ID | Full Name |
|----------|-----------|
| `mdd` | District of Maryland |
| `nced` | Eastern District of North Carolina |
| `ncmd` | Middle District of North Carolina |
| `ncwd` | Western District of North Carolina |
| `scd` | District of South Carolina |
| `vaed` | Eastern District of Virginia |
| `vawd` | Western District of Virginia |
| `wvnd` | Northern District of West Virginia |
| `wvsd` | Southern District of West Virginia |

### Fifth Circuit
| Court ID | Full Name |
|----------|-----------|
| `laed` | Eastern District of Louisiana |
| `lamd` | Middle District of Louisiana |
| `lawd` | Western District of Louisiana |
| `msnd` | Northern District of Mississippi |
| `mssd` | Southern District of Mississippi |
| `txed` | Eastern District of Texas |
| `txnd` | Northern District of Texas |
| `txsd` | Southern District of Texas |
| `txwd` | Western District of Texas |

### Sixth Circuit
| Court ID | Full Name |
|----------|-----------|
| `kyed` | Eastern District of Kentucky |
| `kywd` | Western District of Kentucky |
| `mied` | Eastern District of Michigan |
| `miwd` | Western District of Michigan |
| `ohnd` | Northern District of Ohio |
| `ohsd` | Southern District of Ohio |
| `tned` | Eastern District of Tennessee |
| `tnmd` | Middle District of Tennessee |
| `tnwd` | Western District of Tennessee |

### Seventh Circuit
| Court ID | Full Name |
|----------|-----------|
| `ilcd` | Central District of Illinois |
| `ilnd` | Northern District of Illinois |
| `ilsd` | Southern District of Illinois |
| `innd` | Northern District of Indiana |
| `insd` | Southern District of Indiana |
| `wied` | Eastern District of Wisconsin |
| `wiwd` | Western District of Wisconsin |

### Eighth Circuit
| Court ID | Full Name |
|----------|-----------|
| `ared` | Eastern District of Arkansas |
| `arwd` | Western District of Arkansas |
| `iaed` | (historical) |
| `iand` | Northern District of Iowa |
| `iasd` | Southern District of Iowa |
| `mnd` | District of Minnesota |
| `moed` | Eastern District of Missouri |
| `mowd` | Western District of Missouri |
| `ned` | District of Nebraska |
| `ndd` | District of North Dakota |
| `sdd` | District of South Dakota |

### Ninth Circuit
| Court ID | Full Name |
|----------|-----------|
| `akd` | District of Alaska |
| `azd` | District of Arizona |
| `cacd` | Central District of California |
| `caed` | Eastern District of California |
| `cand` | Northern District of California |
| `casd` | Southern District of California |
| `hid` | District of Hawaii |
| `idd` | District of Idaho |
| `mtd` | District of Montana |
| `nvd` | District of Nevada |
| `ord` | District of Oregon |
| `waed` | Eastern District of Washington |
| `wawd` | Western District of Washington |
| `gud` | District of Guam |
| `nmid` | District of the Northern Mariana Islands |

### Tenth Circuit
| Court ID | Full Name |
|----------|-----------|
| `cod` | District of Colorado |
| `ksd` | District of Kansas |
| `nmd` | District of New Mexico |
| `oked` | Eastern District of Oklahoma |
| `oknd` | Northern District of Oklahoma |
| `okwd` | Western District of Oklahoma |
| `utd` | District of Utah |
| `wyd` | District of Wyoming |

### Eleventh Circuit
| Court ID | Full Name |
|----------|-----------|
| `almd` | Middle District of Alabama |
| `alnd` | Northern District of Alabama |
| `alsd` | Southern District of Alabama |
| `flmd` | Middle District of Florida |
| `flnd` | Northern District of Florida |
| `flsd` | Southern District of Florida |
| `gamd` | Middle District of Georgia |
| `gand` | Northern District of Georgia |
| `gasd` | Southern District of Georgia |

### D.C. Circuit
| Court ID | Full Name |
|----------|-----------|
| `dcd` | District of Columbia |

---

## Specialized Federal Courts (Federal Special - `FS`)

| Court ID | Full Name |
|----------|-----------|
| `cit` | Court of International Trade |
| `cofc` | Court of Federal Claims |
| `tax` | United States Tax Court |
| `uscfc` | Court of Federal Claims |
| `armfor` | Court of Appeals for the Armed Forces |
| `mc` | Military Commission |
| `mspb` | Merit Systems Protection Board |
| `nmcca` | Navy-Marine Corps Court of Criminal Appeals |
| `acca` | Army Court of Criminal Appeals |
| `afcca` | Air Force Court of Criminal Appeals |
| `cgcca` | Coast Guard Court of Criminal Appeals |
| `bva` | Board of Veterans' Appeals |
| `eca` | Court of Appeals for Veterans Claims |
| `fiscr` | Foreign Intelligence Surveillance Court of Review |
| `fisc` | Foreign Intelligence Surveillance Court |
| `jpml` | Judicial Panel on Multidistrict Litigation |
| `cc` | Commerce Court |
| `cusc` | Customs Court |
| `ccpa` | Court of Customs and Patent Appeals |

---

## Bankruptcy Courts (Federal Bankruptcy - `FB`)

Bankruptcy courts follow the pattern: `{district_id}b`

| Court ID | Full Name |
|----------|-----------|
| `almb` | Bankruptcy Court, M.D. Alabama |
| `alnb` | Bankruptcy Court, N.D. Alabama |
| `alsb` | Bankruptcy Court, S.D. Alabama |
| `akb` | Bankruptcy Court, D. Alaska |
| `azb` | Bankruptcy Court, D. Arizona |
| `areb` | Bankruptcy Court, E.D. Arkansas |
| `arwb` | Bankruptcy Court, W.D. Arkansas |
| `cacb` | Bankruptcy Court, C.D. California |
| `caeb` | Bankruptcy Court, E.D. California |
| `canb` | Bankruptcy Court, N.D. California |
| `casb` | Bankruptcy Court, S.D. California |
| `cob` | Bankruptcy Court, D. Colorado |
| `ctb` | Bankruptcy Court, D. Connecticut |
| `deb` | Bankruptcy Court, D. Delaware |
| `dcb` | Bankruptcy Court, D.C. |
| `flmb` | Bankruptcy Court, M.D. Florida |
| `flnb` | Bankruptcy Court, N.D. Florida |
| `flsb` | Bankruptcy Court, S.D. Florida |
| `gamb` | Bankruptcy Court, M.D. Georgia |
| `ganb` | Bankruptcy Court, N.D. Georgia |
| `gasb` | Bankruptcy Court, S.D. Georgia |
| `hib` | Bankruptcy Court, D. Hawaii |
| `idb` | Bankruptcy Court, D. Idaho |
| `ilcb` | Bankruptcy Court, C.D. Illinois |
| `ilnb` | Bankruptcy Court, N.D. Illinois |
| `ilsb` | Bankruptcy Court, S.D. Illinois |
| `innb` | Bankruptcy Court, N.D. Indiana |
| `insb` | Bankruptcy Court, S.D. Indiana |
| `ianb` | Bankruptcy Court, N.D. Iowa |
| `iasb` | Bankruptcy Court, S.D. Iowa |
| `ksb` | Bankruptcy Court, D. Kansas |
| `kyeb` | Bankruptcy Court, E.D. Kentucky |
| `kywb` | Bankruptcy Court, W.D. Kentucky |
| `laeb` | Bankruptcy Court, E.D. Louisiana |
| `lamb` | Bankruptcy Court, M.D. Louisiana |
| `lawb` | Bankruptcy Court, W.D. Louisiana |
| `meb` | Bankruptcy Court, D. Maine |
| `mdb` | Bankruptcy Court, D. Maryland |
| `mab` | Bankruptcy Court, D. Massachusetts |
| `mieb` | Bankruptcy Court, E.D. Michigan |
| `miwb` | Bankruptcy Court, W.D. Michigan |
| `mnb` | Bankruptcy Court, D. Minnesota |
| `msnb` | Bankruptcy Court, N.D. Mississippi |
| `mssb` | Bankruptcy Court, S.D. Mississippi |
| `moeb` | Bankruptcy Court, E.D. Missouri |
| `mowb` | Bankruptcy Court, W.D. Missouri |
| `mtb` | Bankruptcy Court, D. Montana |
| `neb` | Bankruptcy Court, D. Nebraska |
| `nvb` | Bankruptcy Court, D. Nevada |
| `nhb` | Bankruptcy Court, D. New Hampshire |
| `njb` | Bankruptcy Court, D. New Jersey |
| `nmb` | Bankruptcy Court, D. New Mexico |
| `nyeb` | Bankruptcy Court, E.D. New York |
| `nynb` | Bankruptcy Court, N.D. New York |
| `nysb` | Bankruptcy Court, S.D. New York |
| `nywb` | Bankruptcy Court, W.D. New York |
| `nceb` | Bankruptcy Court, E.D. North Carolina |
| `ncmb` | Bankruptcy Court, M.D. North Carolina |
| `ncwb` | Bankruptcy Court, W.D. North Carolina |
| `ndb` | Bankruptcy Court, D. North Dakota |
| `ohnb` | Bankruptcy Court, N.D. Ohio |
| `ohsb` | Bankruptcy Court, S.D. Ohio |
| `okeb` | Bankruptcy Court, E.D. Oklahoma |
| `oknb` | Bankruptcy Court, N.D. Oklahoma |
| `okwb` | Bankruptcy Court, W.D. Oklahoma |
| `orb` | Bankruptcy Court, D. Oregon |
| `paeb` | Bankruptcy Court, E.D. Pennsylvania |
| `pamb` | Bankruptcy Court, M.D. Pennsylvania |
| `pawb` | Bankruptcy Court, W.D. Pennsylvania |
| `prb` | Bankruptcy Court, D. Puerto Rico |
| `rib` | Bankruptcy Court, D. Rhode Island |
| `scb` | Bankruptcy Court, D. South Carolina |
| `sdb` | Bankruptcy Court, D. South Dakota |
| `tneb` | Bankruptcy Court, E.D. Tennessee |
| `tnmb` | Bankruptcy Court, M.D. Tennessee |
| `tnwb` | Bankruptcy Court, W.D. Tennessee |
| `txeb` | Bankruptcy Court, E.D. Texas |
| `txnb` | Bankruptcy Court, N.D. Texas |
| `txsb` | Bankruptcy Court, S.D. Texas |
| `txwb` | Bankruptcy Court, W.D. Texas |
| `utb` | Bankruptcy Court, D. Utah |
| `vtb` | Bankruptcy Court, D. Vermont |
| `vaeb` | Bankruptcy Court, E.D. Virginia |
| `vawb` | Bankruptcy Court, W.D. Virginia |
| `waeb` | Bankruptcy Court, E.D. Washington |
| `wawb` | Bankruptcy Court, W.D. Washington |
| `wvnb` | Bankruptcy Court, N.D. West Virginia |
| `wvsb` | Bankruptcy Court, S.D. West Virginia |
| `wieb` | Bankruptcy Court, E.D. Wisconsin |
| `wiwb` | Bankruptcy Court, W.D. Wisconsin |
| `wyb` | Bankruptcy Court, D. Wyoming |

---

## Filtering by Court in the API

### Single court
```
GET /api/rest/v4/dockets/?court=nysd
```

### Multiple courts (comma-separated)
```
GET /api/rest/v4/dockets/?court__in=nysd,nyed,njd
```

### By jurisdiction type
```
GET /api/rest/v4/dockets/?court__jurisdiction=FD
```

### Exclusion
```
GET /api/rest/v4/dockets/?court__jurisdiction!=FB
```

### In Search API
```
GET /api/rest/v4/search/?type=d&court=nysd
GET /api/rest/v4/search/?type=d&court=nysd nyed njd
```

**Note:** The search API expands court queries to include child courts (e.g., searching a circuit includes its districts). The database API does NOT do this -- it returns exactly what you ask for.

---

## Sources
- CourtListener Jurisdictions: https://www.courtlistener.com/help/api/jurisdictions/
- Courts-DB GitHub: https://github.com/freelawproject/courts-db
- CourtListener API docs: https://www.courtlistener.com/help/api/rest/
