#!/usr/bin/env python3
"""
ECI Live Data Fetcher — GitHub Actions
Fetches from results.eci.gov.in using browser-like headers
"""
import urllib.request, urllib.error, json, re, time, sys
from datetime import datetime

ELECTIONS = {
    "May2026Gen": {
        "label": "Assembly Elections — May 2026",
        "base": "https://results.eci.gov.in/ResultAcGenMay2026",
        "states": [
            {"name":"Tamil Nadu",  "code":"S22","total":234},
            {"name":"West Bengal", "code":"S25","total":294},
            {"name":"Assam",       "code":"S03","total":126},
            {"name":"Kerala",      "code":"S11","total":140},
            {"name":"Puducherry",  "code":"U07","total":30},
        ]
    },
    "Feb2025": {
        "label": "Delhi Assembly — Feb 2025",
        "base": "https://results.eci.gov.in/ResultAcGenFeb2025",
        "states": [{"name":"Delhi","code":"U05","total":70}]
    },
    "Nov2024": {
        "label": "Assembly Elections — Nov 2024",
        "base": "https://results.eci.gov.in/ResultAcGenNov2024",
        "states": [
            {"name":"Maharashtra","code":"S13","total":288},
            {"name":"Jharkhand",  "code":"S08","total":81},
        ]
    }
}

PARTY_COLORS = {
    "BJP":"#f97316","INC":"#3b82f6","TVK":"#7c3aed","ADMK":"#16a34a",
    "DMK":"#b91c1c","TMC":"#7c3aed","AITC":"#7c3aed","AAP":"#22c55e",
    "SP":"#ea580c","CPI(M)":"#dc2626","CPI":"#ef4444","IUML":"#0891b2",
    "PMK":"#d97706","KEC":"#0e7490","AGP":"#65a30d","AIUDF":"#c026d3",
    "BOPF":"#0891b2","JMM":"#16a34a","RJD":"#c026d3","TDP":"#2563eb",
    "JDU":"#059669","AINRC":"#7c2d12","RSP":"#7c3aed","VCK":"#be185d",
    "BJP(A)":"#f97316","AJUP":"#0891b2","AISF":"#ef4444","ASMJTYP":"#f59e0b",
    "SS(S)":"#d97706","NCP(A)":"#8b5cf6","SS(UBT)":"#a21caf","NCP":"#0891b2",
    "IND":"#6b7280","OTH":"#6b7280",
}

HEADERS = [
    # Try multiple UA strings — ECI blocks some
    {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-IN,en;q=0.9,hi;q=0.8","Referer":"https://results.eci.gov.in/","Cache-Control":"no-cache"},
    {"User-Agent":"python-requests/2.31.0","Accept":"*/*","Accept-Encoding":"gzip, deflate"},
    {"User-Agent":"curl/7.88.1","Accept":"*/*"},
]

def fetch(url):
    for hdrs in HEADERS:
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=20) as r:
                html = r.read().decode("utf-8","replace")
                if len(html) > 1000:
                    return html
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5)
        except Exception:
            pass
        time.sleep(1)
    return None

def parse(html, name, total):
    parties = []
    # Table parse
    tbl = re.search(r'Party Wise Results.*?(<table.*?</table>)', html, re.S|re.I)
    if tbl:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl.group(1), re.S|re.I)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S|re.I)
            cells = [re.sub(r'<[^>]+>','',c).strip() for c in cells]
            cells = [c for c in cells if c and c not in ['–','-','—']]
            if len(cells) < 3: continue
            full = cells[0]
            if full.lower() in ['total','party','parties']: continue
            am = re.search(r'-\s*([A-Z()\d]+)\s*$', full)
            abbr = am.group(1) if am else full.replace(' ','')[:8].upper()
            try:
                won = int(re.sub(r'\D','',cells[1]) or '0')
                lead = int(re.sub(r'\D','',cells[2]) or '0')
            except: continue
            if won+lead > 0:
                parties.append({"abbr":abbr,"full":full,"won":won,"leading":lead,
                                "total":won+lead,"color":PARTY_COLORS.get(abbr,"#6b7280")})
    parties.sort(key=lambda x:x["total"], reverse=True)
    tm = re.search(r'(\d+)\*?\s*/\s*'+str(total), html)
    counted = int(tm.group(1)) if tm else sum(p["total"] for p in parties)
    lu = re.search(r'Last Updated[^<]*?(\d{1,2}:\d{2}\s*[AP]M[^<]*?\d{2}/\d{2}/\d{4})', html, re.I)
    return {"name":name,"total":total,"counted":min(counted,total),
            "majority":(total//2)+1,"last_updated":lu.group(1).strip() if lu else "",
            "parties":parties}

# Load existing data.json for fallback
try:
    with open("data.json","r") as f:
        existing = json.load(f)
except:
    existing = {"elections":{}}

output = {
    "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    "generated_ist": datetime.now().strftime("%I:%M %p, %d %b %Y"),
    "elections": {}
}

for eid, el in ELECTIONS.items():
    print(f"\n=== {el['label']} ===")
    states = []
    for s in el["states"]:
        url = f"{el['base']}/partywiseresult-{s['code']}.htm"
        print(f"  {s['name']}... ", end="", flush=True)
        html = fetch(url)
        if html:
            data = parse(html, s["name"], s["total"])
            if data["parties"]:
                states.append(data)
                print(f"OK — {data['parties'][0]['abbr']} {data['parties'][0]['total']}")
                continue
        # Fallback to existing
        ex_states = existing.get("elections",{}).get(eid,{}).get("states",[])
        fb = next((x for x in ex_states if x["name"]==s["name"]), None)
        if fb:
            states.append(fb)
            print("FAIL — using cached data")
        else:
            print("FAIL — no cache")
    output["elections"][eid] = {"label":el["label"],"states":states}

# LS2024 — static final data
output["elections"]["LS2024"] = existing.get("elections",{}).get("LS2024", {
    "label":"Lok Sabha 2024","states":[{
        "name":"India — Lok Sabha","total":543,"counted":543,"majority":272,
        "last_updated":"June 2024 — Final",
        "parties":[
            {"abbr":"BJP","full":"BJP","won":240,"leading":0,"total":240,"color":"#f97316"},
            {"abbr":"INC","full":"INC","won":99,"leading":0,"total":99,"color":"#3b82f6"},
            {"abbr":"SP","full":"SP","won":37,"leading":0,"total":37,"color":"#ea580c"},
            {"abbr":"TMC","full":"TMC","won":29,"leading":0,"total":29,"color":"#7c3aed"},
            {"abbr":"DMK","full":"DMK","won":22,"leading":0,"total":22,"color":"#b91c1c"},
            {"abbr":"TDP","full":"TDP","won":16,"leading":0,"total":16,"color":"#2563eb"},
            {"abbr":"JDU","full":"JDU","won":12,"leading":0,"total":12,"color":"#059669"},
            {"abbr":"OTH","full":"Others","won":88,"leading":0,"total":88,"color":"#6b7280"},
        ]
    }]
})

with open("data.json","w",encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"\n✓ data.json saved — {datetime.now().strftime('%H:%M:%S')}")
