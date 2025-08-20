# iata_codes.py

import json
from pathlib import Path
from rapidfuzz import process

IATA_CODES = {
    "mumbai": "BOM",
    "delhi": "DEL",
    "new york": "JFK",
    "los angeles": "LAX",
    "london": "LHR",
    "paris": "CDG",
    "dubai": "DXB",
    "singapore": "SIN",
    "tokyo": "NRT",
    "bangkok": "BKK",
    "amsterdam": "AMS",
    "frankfurt": "FRA",
    "hong kong": "HKG",
    "toronto": "YYZ",
    "sydney": "SYD",
    "chicago": "ORD",
    "san francisco": "SFO",
    "seattle": "SEA",
    "beijing": "PEK",
    "shanghai": "PVG",
    "seoul": "ICN",
    "madrid": "MAD",
    "barcelona": "BCN",
    "rome": "FCO",
    "zurich": "ZRH",
    "vienna": "VIE",
    "doha": "DOH",
    "manila": "MNL",
    "istanbul": "IST",
    "sao paulo": "GRU",
    "buenos aires": "EZE",
    "johannesburg": "JNB",
    "cape town": "CPT",
    "auckland": "AKL",
    "melbourne": "MEL",
    "vancouver": "YVR",
    "montreal": "YUL",
    "cairo": "CAI",
    "athens": "ATH",
    "lisbon": "LIS",
    "helsinki": "HEL",
    "oslo": "OSL",
    "stockholm": "ARN",
    "copenhagen": "CPH",
    "warsaw": "WAW",
    "prague": "PRG",
    "budapest": "BUD",
    "moscow": "SVO",
    "doha": "DOH",
    "riyadh": "RUH",
    "kuwait city": "KWI",
    "karachi": "KHI",
    "lahore": "LHE",
    "colombo": "CMB",
    "kathmandu": "KTM",
    "yangon": "RGN",
    "hanoi": "HAN",
    "ho chi minh": "SGN",
    "jakarta": "CGK",
    "kuala lumpur": "KUL",
    "taipei": "TPE",
    "manchester": "MAN",
    "birmingham": "BHX",
    "edinburgh": "EDI",
    "glasgow": "GLA",
    "brussels": "BRU",
    "munich": "MUC",
    "hamburg": "HAM",
    "stuttgart": "STR",
    "berlin": "BER",
    "geneva": "GVA",
    "nice": "NCE",
    "lyon": "LYS",
    "marseille": "MRS",
    "venice": "VCE",
    "milan": "MXP",
    "naples": "NAP",
    "osaka": "KIX",
    "kyoto": "UKY",
    "nagoya": "NGO",
    "fukuoka": "FUK",
    "sapporo": "CTS",
    "delhi": "DEL",
    "chennai": "MAA",
    "kolkata": "CCU",
    "bengaluru": "BLR",
    "hyderabad": "HYD",
    "ahmedabad": "AMD",
    "pune": "PNQ",
    "goa": "GOI",
    "kochi": "COK",
    "trivandrum": "TRV",
    "indore": "IDR",
    "jaipur": "JAI",
    "lucknow": "LKO",
    "varanasi": "VNS",
    "nagpur": "NAG",
    "patna": "PAT",
    "bhubaneswar": "BBI",
    "raipur": "RPR",
    "srinagar": "SXR",
    "amritsar": "ATQ",
    "ranchi": "IXR",
    "guwahati": "GAU",
    "dehradun": "DED",
    "udaipur": "UDR",
    "aurangabad": "IXU",
    "mysore": "MYQ",
    "surat": "STV",
    "rajkot": "RAJ",
    "vadodara": "BDQ",
    "jodhpur": "JDH",
    "madurai": "IXM",
    "tiruchirappalli": "TRZ",
    "coimbatore": "CJB",
    "vizag": "VTZ",
    "agartala": "IXA",
    "dimapur": "DMU",
    "shillong": "SHL",
    "imphal": "IMF",
    "aizawl": "AJL",
    "silchar": "IXS",
    "bagdogra": "IXB"
    # Add more if needed up to 200
}

# Common aliases and misspellings mapped to canonical names
CITY_ALIASES = {
    "bangalore": "bengaluru",
    "benagluru": "bengaluru",
    "bombay": "mumbai",
    "madras": "chennai",
    "calcutta": "kolkata",
    "mumabi": "mumbai",
    "delhii": "delhi",
    "chenai": "chennai",
    "hydrabad": "hyderabad",
    "new delhi": "delhi",
    # Add more based on user input logs
}

# Store new alias suggestions for review
ALIAS_LOG_FILE = Path("./alias_suggestions.json")

# Thresholds
FUZZY_MATCH_THRESHOLD = 85


def get_iata_code(city_name):
    original_input = city_name
    city = city_name.lower().strip()

    # Step 1: Check direct alias match
    if city in CITY_ALIASES:
        print(f"🔁 Correct match: '{original_input}' → '{CITY_ALIASES[city]}'")
        city = CITY_ALIASES[city]

    # Step 2: Check IATA_CODES
    if city in IATA_CODES:
        #print(f"✅ Found IATA code for '{city}': {IATA_CODES[city]}")
        return IATA_CODES[city]

    # Step 3: Try fuzzy alias match if not directly in aliases
    alias_match, alias_score, _ = process.extractOne(city, CITY_ALIASES.keys())
    if alias_score >= 90:
        canonical = CITY_ALIASES[alias_match]
        print(f"🔍 Fuzzy alias match: '{city}' → '{alias_match}' → '{canonical}'")
        if canonical in IATA_CODES:
            #print(f"✅ Found IATA code for '{canonical}': {IATA_CODES[canonical]}")
            return IATA_CODES[canonical]

    # Step 4: Try fuzzy match directly against IATA_CODES
    match, score, _ = process.extractOne(city, IATA_CODES.keys())
    if score >= FUZZY_MATCH_THRESHOLD:
        print(f"🔍 Fuzzy IATA match: '{city}' → '{match}' (score: {score})")
        return IATA_CODES[match]

    print(f"❌ IATA code not found for '{original_input}' in local database.")
    #_log_unknown_city(city)
    return None

