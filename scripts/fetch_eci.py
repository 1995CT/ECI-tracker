#!/usr/bin/env python3
"""
ECI Live Data Fetcher
Runs via GitHub Actions every 5 minutes
Fetches official ECI results pages and saves clean JSON
"""
import urllib.request
import json
import re
import os
from datetime import datetime
from html.parser import HTMLParser

ELECTIONS = [
    {
        "id": "May2026Gen",
        "label": "Assembly Elections — May 2026",
        "states": [
            {"name": "Tamil Nadu",   "code": "S22", "total": 234},
            {"name": "West Bengal",  "code": "S25", "total": 294},
            {"name": "Assam",        "code": "S03", "total": 126},
            {"name": "Kerala",       "code": "S11", "total": 140},
            {"name": "Puducherry",   "code": "U07", "total": 30},
        ],
        "base_url": "https://results.eci.gov.in/ResultAcGenMay2026/partywiseresult-{code}.htm"
    },
    {
        "id": "Feb2025",
        "label": "Delhi Assembly — Feb 2025",
        "states": [
            {"name": "Delhi", "code": "U05", "total": 70},
        ],
        "base_url": "https://results.eci.gov.in/ResultAcGenFeb2025/partywiseresult-{code}.htm"
    },
    {
        "id": "Nov2024",
        "label": "Assembly Elections — Nov 2024",
        "states": [
            {"name": "Maharashtra", "code": "S13", "total": 288},
            {"name": "Jharkhand",   "code": "S08", "total": 81},
        ],
        "base_url": "https://results.eci.gov.in/ResultAcGenNov2024/partywiseresult-{code}.htm"
    },
    {
        "id": "LS2024",
        "label": "Lok Sabha — 2024",
        "states": [
            {"name": "India (Lok Sabha)", "code": "all", "total": 543},
        ],
        "base_url": "https://results.eci.gov.in/ResultGE2024/index.htm"
    }
]

PARTY_COLORS = {
    "BJP": "#f97316", "INC": "#3b82f6", "TVK": "#7c3aed",
    "ADMK": "#16a34a", "DMK": "#b91c1c", "TMC": "#7c3aed",
    "AITC": "#7c3aed", "AAP": "#22c55e", "SP": "#ea580c",
    "CPI(M)": "#dc2626", "CPI": "#ef4444", "IUML": "#0891b2",
    "PMK": "#d97706", "KEC": "#0e7490", "AGP": "#65a30d",
    "AIUDF": "#c026d3", "BOPF": "#0891b2", "JMM": "#16a34a",
    "RJD": "#c026d3", "TDP": "#2563eb", "JDU": "#059669",
    "AINRC": "#7c2d12", "SS": "#d97706", "NCP": "#8b5cf6",
}

def get_color(abbr):
    return PARTY_COLORS.get(abbr, "#6b7280")

def fetch_url(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ElectionBot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://results.eci.gov.in/"
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Fetch error for {url}: {e}")
        return None

def parse_party_table(html, state_name, total_seats):
    """Parse ECI party-wise results HTML table"""
    parties = []
    counted = 0
    last_updated = ""

    # Last updated
    ts_match = re.search(r'Last Updated[^<]*?(\d{1,2}:\d{2}\s*[AP]M[^<]*?\d{2}/\d{2}/\d{4})', html, re.I)
    if ts_match:
        last_updated = ts_match.group(1).strip()

    # Total counted
    total_match = re.search(r'Total AC\s*:\s*(\d+)', html)
    if total_match:
        counted_match = re.search(r'(\d+)\*?\s*/\s*' + re.escape(str(total_seats)), html)
        if counted_match:
            counted = int(counted_match.group(1))

    # Party table rows: look for table rows with Won/Leading/Total
    table_match = re.search(r'Party Wise Results.*?(<table.*?</table>)', html, re.S | re.I)
    if not table_match:
        # fallback: any table with BJP/INC
        table_match = re.search(r'(<table[^>]*>.*?</table>)', html, re.S)

    if table_match:
        table_html = table_match.group(1)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.S | re.I)
        for row in rows:
            cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row, re.S | re.I)
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [c for c in cells if c]
            if len(cells) >= 3:
                full_name = cells[0]
                # Extract abbreviation
                abbr_match = re.search(r'-\s*([A-Z()\d\(\)]+)\s*$', full_name)
                abbr = abbr_match.group(1) if abbr_match else full_name[:6].upper()
                try:
                    won = int(re.sub(r'\D', '', cells[1])) if cells[1] not in ['Won', '-', ''] else 0
                    leading = int(re.sub(r'\D', '', cells[2])) if cells[2] not in ['Leading', '-', ''] else 0
                except:
                    continue
                if full_name.lower() in ['total', 'party', 'parties'] or (won == 0 and leading == 0 and abbr in ['Total', 'TOTAL']):
                    continue
                if won > 0 or leading > 0:
                    parties.append({
                        "abbr": abbr,
                        "full": full_name,
                        "won": won,
                        "leading": leading,
                        "total": won + leading,
                        "color": get_color(abbr)
                    })

    # If no table parsed, try headline numbers from ECI display
    if not parties:
        # ECI shows top parties as ## NUMBER format
        party_blocks = re.findall(r'####\s+([A-Z\(\)]+)\s*##\s*(\d+)', html)
        for abbr, total in party_blocks:
            parties.append({
                "abbr": abbr,
                "full": abbr,
                "won": 0,
                "leading": int(total),
                "total": int(total),
                "color": get_color(abbr)
            })

    # Sort by total seats descending
    parties.sort(key=lambda x: x["total"], reverse=True)

    # Compute counted from declared seats
    if not counted:
        counted = sum(p["total"] for p in parties)

    return {
        "name": state_name,
        "total": total_seats,
        "counted": min(counted, total_seats),
        "majority": (total_seats // 2) + 1,
        "last_updated": last_updated,
        "parties": parties
    }

def fetch_election(election):
    print(f"\n--- Fetching: {election['label']} ---")
    states_data = []
    for s in election["states"]:
        url = election["base_url"].replace("{code}", s["code"])
        print(f"  {s['name']}: {url}")
        html = fetch_url(url)
        if html:
            parsed = parse_party_table(html, s["name"], s["total"])
            states_data.append(parsed)
            print(f"    → {len(parsed['parties'])} parties, {parsed['counted']}/{parsed['total']} counted")
        else:
            print(f"    → FAILED")
    return states_data

def main():
    output = {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "generated_ist": datetime.now().strftime("%I:%M %p, %d %b %Y"),
        "elections": {}
    }

    for election in ELECTIONS:
        states = fetch_election(election)
        output["elections"][election["id"]] = {
            "label": election["label"],
            "states": states
        }

    # Write JSON
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ data.json written at {output['generated_at']}")

if __name__ == "__main__":
    main()
