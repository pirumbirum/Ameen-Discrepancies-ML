# Nature of Suit (NOS) Codes - Complete Reference

Nature of Suit codes are the federal court system's classification system for civil cases. Plaintiffs select one NOS code when filing. These codes are used by PACER, CourtListener, and the FJC Integrated Database.

> **Important:** Plaintiffs can only select ONE code, so cases involving multiple issues may be categorized under a single NOS. Always combine NOS filtering with keyword search for best results.

> **CourtListener field:** `nature_of_suit` (string, max 1000 chars). Stores the **text description** (e.g., `"Securities/Commodities/Exchange"`), NOT the numeric code (850). Free-text from PACER, not a strict enum.
>
> **Critical:** When filtering via the database API, use text matching (`?nature_of_suit__contains=Securities`). When using the Search API, use the `suitNature` field. The exact text varies -- experiment on the front-end first, then replicate in the API.

---

## CONTRACT (110-196)

| Code | Description |
|------|-------------|
| 110 | Insurance |
| 120 | Marine |
| 130 | Miller Act (federal construction bonds) |
| 140 | Negotiable Instrument |
| 150 | Recovery of Overpayment & Enforcement of Judgment |
| 151 | Medicare Act |
| 152 | Recovery of Defaulted Student Loans (Excl. Veterans) |
| 153 | Recovery of Overpayment of Veteran's Benefits |
| 160 | Stockholders' Suits |
| 190 | Other Contract |
| 195 | Contract Product Liability |
| 196 | Franchise |

---

## REAL PROPERTY (210-290)

| Code | Description |
|------|-------------|
| 210 | Land Condemnation |
| 220 | Foreclosure |
| 230 | Rent Lease & Ejectment |
| 240 | Torts to Land |
| 245 | Tort Product Liability |
| 290 | All Other Real Property |

---

## TORTS - PERSONAL INJURY (310-368)

| Code | Description |
|------|-------------|
| 310 | Airplane |
| 315 | Airplane Product Liability |
| 320 | Assault, Libel & Slander |
| 330 | Federal Employers' Liability |
| 340 | Marine |
| 345 | Marine Product Liability |
| 350 | Motor Vehicle |
| 355 | Motor Vehicle Product Liability |
| 360 | Other Personal Injury |
| 362 | Personal Injury - Medical Malpractice |
| 365 | Personal Injury - Product Liability |
| 367 | Health Care/Pharmaceutical Personal Injury Product Liability |
| 368 | Asbestos Personal Injury Product Liability |

---

## TORTS - PERSONAL PROPERTY (370-385)

| Code | Description |
|------|-------------|
| 370 | Other Fraud |
| 371 | Truth in Lending |
| 380 | Other Personal Property Damage |
| 385 | Property Damage Product Liability |

---

## CIVIL RIGHTS (440-448)

| Code | Description |
|------|-------------|
| 440 | Other Civil Rights |
| 441 | Voting |
| 442 | Employment |
| 443 | Housing / Accommodations |
| 444 | Welfare |
| 445 | Americans with Disabilities - Employment |
| 446 | Americans with Disabilities - Other |
| 448 | Education |

---

## PRISONER PETITIONS (510-555)

| Code | Description |
|------|-------------|
| 510 | Motions to Vacate Sentence |
| 530 | General (Habeas Corpus) |
| 535 | Death Penalty (Habeas Corpus) |
| 540 | Mandamus & Other |
| 550 | Civil Rights |
| 555 | Prison Condition |

---

## FORFEITURE/PENALTY (610-690)

| Code | Description |
|------|-------------|
| 610 | Agriculture |
| 620 | Other Food & Drug |
| 625 | Drug Related Seizure of Property (21 USC 881) |
| 630 | Liquor Laws |
| 640 | R.R. & Truck |
| 650 | Airline Regs |
| 660 | Occupational Safety/Health |
| 690 | Other |

---

## LABOR (710-791)

| Code | Description |
|------|-------------|
| 710 | Fair Labor Standards Act |
| 720 | Labor/Management Relations |
| 730 | Labor/Management Reporting & Disclosure Act |
| 740 | Railway Labor Act |
| 751 | Family and Medical Leave Act |
| 790 | Other Labor Litigation |
| 791 | Employee Retirement Income Security Act (ERISA) |

---

## IMMIGRATION (462-465)

| Code | Description |
|------|-------------|
| 462 | Naturalization Application |
| 463 | Habeas Corpus - Alien Detainee |
| 465 | Other Immigration Actions |

---

## PROPERTY RIGHTS / INTELLECTUAL PROPERTY (820-880)

| Code | Description |
|------|-------------|
| 820 | Copyrights |
| 830 | Patent |
| 835 | Patent - Abbreviated New Drug Application |
| 840 | Trademark |
| 880 | Defend Trade Secrets Act of 2016 |

---

## SOCIAL SECURITY (861-865)

| Code | Description |
|------|-------------|
| 861 | HIA (1395ff) |
| 862 | Black Lung (923) |
| 863 | DIWC/DIWW (405(g)) |
| 864 | SSID Title XVI |
| 865 | RSI (405(g)) |

---

## FEDERAL TAX SUITS (870-875)

| Code | Description |
|------|-------------|
| 870 | Taxes (U.S. Plaintiff or Defendant) |
| 871 | IRS - Third Party (26 USC 7609) |
| 875 | Customer Challenge (12 USC 3410) |

---

## BANKRUPTCY (422-423)

| Code | Description |
|------|-------------|
| 422 | Appeal 28 USC 158 |
| 423 | Withdrawal 28 USC 157 |

---

## OTHER STATUTES (400-999)

| Code | Description |
|------|-------------|
| 375 | False Claims Act |
| 376 | Qui Tam (31 USC 3729(a)) |
| 400 | State Reapportionment |
| 410 | Antitrust |
| 430 | Banks and Banking |
| 450 | Commerce / ICC Rates, etc. |
| 460 | Deportation |
| 470 | Racketeer Influenced and Corrupt Organizations (RICO) |
| 480 | Consumer Credit |
| 485 | Telephone Consumer Protection Act |
| 490 | Cable/Sat TV |
| 810 | Selective Service |
| 850 | Securities/Commodities/Exchange |
| 890 | Other Statutory Actions |
| 891 | Agricultural Acts |
| 892 | Economic Stabilization Act |
| 893 | Environmental Matters |
| 894 | Energy Allocation Act |
| 895 | Freedom of Information Act |
| 896 | Arbitration |
| 899 | Administrative Procedure Act / Review or Appeal of Agency Decision |
| 900 | Appeal of Fee Determination Under Equal Access to Justice |
| 910 | Domestic Relations |
| 920 | Insanity (18 USC 4244/4246) |
| 930 | Probate |
| 940 | Substitute Trustee |
| 950 | Constitutionality of State Statutes |
| 990 | Other |
| 992 | Local Jurisdictional Appeal |
| 999 | Miscellaneous / Unclassified |

---

## NOS Codes Most Relevant to Corporate Litigation

### Securities & Financial
| Code | Description | Use Case |
|------|-------------|----------|
| 160 | Stockholders' Suits | Shareholder derivative suits |
| 530 | Securities/Commodities/Exchange | SEC violations, securities fraud |
| 850 | Securities/Commodities/Exchange | Same category, different era |
| 430 | Banks and Banking | Banking disputes |

### Contracts & Commercial
| Code | Description | Use Case |
|------|-------------|----------|
| 110 | Insurance | Corporate insurance disputes |
| 140 | Negotiable Instrument | Commercial paper disputes |
| 190 | Other Contract | General contract disputes |
| 195 | Contract Product Liability | Product liability under contract |
| 196 | Franchise | Franchise agreement disputes |

### Intellectual Property
| Code | Description | Use Case |
|------|-------------|----------|
| 820 | Copyrights | Copyright infringement |
| 830 | Patent | Patent infringement |
| 835 | Patent - ANDA | Pharmaceutical patent |
| 840 | Trademark | Trademark disputes |
| 880 | Defend Trade Secrets Act | Trade secret misappropriation |

### Antitrust & RICO
| Code | Description | Use Case |
|------|-------------|----------|
| 410 | Antitrust | Price fixing, monopoly, competition |
| 470 | RICO | Racketeering, organized fraud |

### Employment (Corporate Defendants)
| Code | Description | Use Case |
|------|-------------|----------|
| 442 | Employment (Civil Rights) | Discrimination lawsuits |
| 445 | ADA - Employment | ADA employment claims |
| 710 | Fair Labor Standards Act | Wage/hour claims |
| 720 | Labor/Management Relations | Union disputes |
| 791 | ERISA | Employee benefits disputes |

### Product Liability
| Code | Description | Use Case |
|------|-------------|----------|
| 245 | Tort Product Liability (Real Property) | Real property product defects |
| 315 | Airplane Product Liability | Aviation product defects |
| 345 | Marine Product Liability | Maritime product defects |
| 355 | Motor Vehicle Product Liability | Auto product defects |
| 365 | Personal Injury - Product Liability | General product liability |
| 367 | Pharmaceutical Product Liability | Drug/device liability |
| 368 | Asbestos Product Liability | Asbestos claims |
| 385 | Property Damage Product Liability | Property damage from products |

### Environmental
| Code | Description | Use Case |
|------|-------------|----------|
| 893 | Environmental Matters | EPA, CERCLA, Clean Water Act |

### Tax (Corporate)
| Code | Description | Use Case |
|------|-------------|----------|
| 870 | Taxes | Corporate tax disputes |
| 871 | IRS - Third Party | IRS summons, third-party |

### Fraud & Consumer
| Code | Description | Use Case |
|------|-------------|----------|
| 370 | Other Fraud | General fraud claims |
| 375 | False Claims Act | Government fraud |
| 376 | Qui Tam | Whistleblower suits |
| 480 | Consumer Credit | Consumer lending disputes |
| 485 | Telephone Consumer Protection Act | TCPA robocall suits |

### Bankruptcy
| Code | Description | Use Case |
|------|-------------|----------|
| 422 | Bankruptcy Appeal | Bankruptcy appeals |
| 423 | Bankruptcy Withdrawal | Withdrawn from bankruptcy court |

---

## How NOS Codes Appear in CourtListener

### On the Docket Object
```json
{
    "nature_of_suit": "190 Contract: Other",
    "cause": "28:1332 Diversity-Contract Dispute"
}
```

### Filtering by NOS
```
GET /api/rest/v4/dockets/?nature_of_suit=190
GET /api/rest/v4/dockets/?nature_of_suit=190&court=nysd
```

### In Search API
Use the `suitNature` field (camelCase in search):
```
GET /api/rest/v4/search/?type=d&suitNature=190
```

### Exclusion Filter
```
GET /api/rest/v4/dockets/?!nature_of_suit=550
```

---

## Appellate Court NOS Codes
Circuit courts sometimes use **4-digit** NOS codes, adding a prefix digit:
- District court NOS `445` -> Court of appeals might use `1445`, `2445`, or `3445`
- The prefix digit varies by circuit

---

## Sources
- PACER: https://pacer.uscourts.gov/sites/default/files/files/nature%20of%20suit%20codes.pdf
- US Courts: https://www.uscourts.gov/sites/default/files/js_044_code_descriptions.pdf
- Second Circuit reference: https://www.ca2.uscourts.gov/clerk/case_filing/electronic_filing/how_to_use_cmecf/nature_of_suit_codes.html
- CourtListener PACER API: https://www.courtlistener.com/help/api/rest/pacer/
