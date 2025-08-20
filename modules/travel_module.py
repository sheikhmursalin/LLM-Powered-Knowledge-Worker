# travel_module.py

import os
import re
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from modules.iata_codes import IATA_CODES, get_iata_code
import dateparser
from dateparser.search import search_dates

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "google-flights2.p.rapidapi.com"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST
}

def extract_flight_details(prompt):
    """
    Enhanced flight detail extraction with better regex patterns
    """
    # Clean the prompt
    prompt = prompt.strip().lower()
    
    # Try multiple patterns for "from X to Y" with various date formats
    patterns = [
        # "from tokyo to mumbai on 30 august"
        r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)\s+(?:on|for|at)\s+(.+?)(?:\s|$)",
        # "from tokyo to mumbai 30 august"
        r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)\s+([0-9]{1,2}\s+[a-zA-Z]+(?:\s+[0-9]{4})?)",
        # "from tokyo to mumbai 2025-08-30"
        r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)\s+([0-9]{4}-[0-9]{2}-[0-9]{2})",
        # "from tokyo to mumbai tomorrow"
        r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)\s+(tomorrow|today|yesterday)",
        # Basic pattern without specific date keywords
        r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+?)(?:\s+(.+?))?$"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, prompt, re.IGNORECASE)
        if match:
            origin_city = match.group(1).strip()
            destination_city = match.group(2).strip()
            date_str = match.group(3).strip() if match.group(3) else None
            
            # Clean up city names - remove common words that might be captured
            origin_city = clean_city_name(origin_city)
            destination_city = clean_city_name(destination_city)
            
            return origin_city, destination_city, date_str
    
    # If no pattern matches, try to extract cities and dates separately
    return extract_separate_components(prompt)

def clean_city_name(city_name):
    """Clean city names by removing common words that shouldn't be part of the city name"""
    if not city_name:
        return city_name
        
    # Remove common words that might be accidentally captured
    stop_words = ['on', 'for', 'at', 'the', 'in', 'to', 'from']
    words = city_name.split()
    cleaned_words = [word for word in words if word.lower() not in stop_words]
    return ' '.join(cleaned_words)

def extract_separate_components(prompt):
    """Extract cities and dates separately if main patterns fail"""
    # Find cities pattern
    cities_match = re.search(r"from\s+([a-zA-Z\s]+?)\s+to\s+([a-zA-Z\s]+)", prompt, re.IGNORECASE)
    
    if cities_match:
        origin_city = clean_city_name(cities_match.group(1).strip())
        destination_city = clean_city_name(cities_match.group(2).strip())
        
        # Look for dates anywhere in the prompt
        date_str = extract_date_from_text(prompt)
        
        return origin_city, destination_city, date_str
    
    return None, None, None

def extract_date_from_text(text):
    """Extract date from text using multiple approaches"""
    # Try ISO format first
    iso_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if iso_match:
        return iso_match.group(0)
    
    # Try relative dates
    relative_match = re.search(r"\b(tomorrow|today|yesterday|next\s+\w+|this\s+\w+)\b", text, re.IGNORECASE)
    if relative_match:
        return relative_match.group(1)
    
    # Try day month format (30 august, 15 december, etc.)
    day_month_match = re.search(r"\b([0-9]{1,2})\s+([a-zA-Z]+)(?:\s+([0-9]{4}))?\b", text, re.IGNORECASE)
    if day_month_match:
        day = day_month_match.group(1)
        month = day_month_match.group(2)
        year = day_month_match.group(3) if day_month_match.group(3) else str(datetime.now().year)
        return f"{day} {month} {year}"
    
    # Try month day format (august 30, december 15, etc.)
    month_day_match = re.search(r"\b([a-zA-Z]+)\s+([0-9]{1,2})(?:\s+([0-9]{4}))?\b", text, re.IGNORECASE)
    if month_day_match:
        month = month_day_match.group(1)
        day = month_day_match.group(2)
        year = month_day_match.group(3) if month_day_match.group(3) else str(datetime.now().year)
        return f"{day} {month} {year}"
    
    return None

def format_date(date_str):
    """Enhanced date formatting with better parsing"""
    if not date_str:
        return None
        
    date_str = date_str.strip()
    
    # Handle relative dates first
    if date_str.lower() in ['today']:
        return datetime.now().strftime("%Y-%m-%d")
    elif date_str.lower() in ['tomorrow']:
        return (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    elif date_str.lower() in ['yesterday']:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    # Try using dateparser for complex dates
    try:
        parsed_date = dateparser.parse(date_str, settings={'PREFER_DATES_FROM': 'future'})
        if parsed_date:
            return parsed_date.strftime("%Y-%m-%d")
    except:
        pass
    
    # Try ISO format
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
    
    # Try various date formats
    formats = [
        "%d %B %Y",      # 30 August 2025
        "%d %b %Y",      # 30 Aug 2025
        "%d %B",         # 30 August
        "%d %b",         # 30 Aug
        "%B %d %Y",      # August 30 2025
        "%b %d %Y",      # Aug 30 2025
        "%B %d",         # August 30
        "%b %d",         # Aug 30
        "%d/%m/%Y",      # 30/08/2025
        "%d-%m-%Y",      # 30-08-2025
        "%m/%d/%Y",      # 08/30/2025
        "%m-%d-%Y",      # 08-30-2025
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # If no year specified, assume current year
            if dt.year == 1900:
                dt = dt.replace(year=datetime.now().year)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return None

def print_flight_results(data):
    output = []
    output.append(f"✈️ <b>FLIGHT SEARCH RESULTS</b><br>")
    if not data.get("status", True):
        output.append(f"❌ <b>API Error:</b> {data.get('message', 'Unknown error')}<br>")
        return "".join(output)

    itineraries = data.get("data", {}).get("itineraries", {})
    flights = itineraries.get("topFlights") or itineraries.get("flights", [])

    if not flights:
        output.append("❌ <b>No flights found in the response.</b><br>")
        return "".join(output)

    output.append(f"<b>Found {len(flights)} flight option(s):</b><br>")

    for i, flight in enumerate(flights, 1):
        output.append(f"<b>✈️ Flight {i}</b><br>")
        output.append(f"<b>🛫 Departure:</b> {flight.get('departure_time', 'Unknown')}<br>")
        output.append(f"<b>🛬 Arrival:</b> {flight.get('arrival_time', 'Unknown')}<br>")
        duration = flight.get("duration", {})
        output.append(f"<b>⏱️ Duration:</b> {duration.get('text', 'Unknown')}<br>")
        for j, segment in enumerate(flight.get("flights", [])):
            output.append(f"<b>Segment {j+1}:</b><br>")
            output.append(f"🏷️ <b>Airline:</b> {segment.get('airline', 'Unknown Airline')} {segment.get('flight_number', 'Unknown')}<br>")
            output.append(f"🛩️ <b>Aircraft:</b> {segment.get('aircraft', 'Unknown Aircraft')}<br>")
            dep = segment.get('departure_airport', {})
            arr = segment.get('arrival_airport', {})
            output.append(f"🏁 <b>From:</b> {dep.get('airport_name', '')} ({dep.get('airport_code', '')}) at {dep.get('time', '')}<br>")
            output.append(f"🎯 <b>To:</b> {arr.get('airport_name', '')} ({arr.get('airport_code', '')}) at {arr.get('time', '')}<br>")
            output.append(f"💺 <b>Seat:</b> {segment.get('seat', '')} ({segment.get('legroom', '')})<br>")
        price = flight.get("price") or flight.get("total_price", {})
        if isinstance(price, dict):
            output.append(f"💰 <b>Price:</b> Rs. {price.get('value', 'N/A')} {price.get('currency', 'INR')}<br>")
        else:
            output.append(f"💰 <b>Price:</b> {price}<br>")
        bags = flight.get("bags", {})
        output.append(f"🧳 <b>Baggage:</b> {bags.get('carry_on', 0)} carry-on, {bags.get('checked', 0)} checked<br>")
        carbon = flight.get("carbon_emissions", {})
        co2e = carbon.get("CO2e")
        if co2e is not None:
            output.append(f"🌱 <b>Emissions:</b> {co2e / 1000:.0f} kg CO2e ({carbon.get('difference_percent', 0):+d}% vs typical)<br>")
        if flight.get("delay", {}).get("values") is False:
            output.append("✅ <b>On-time performance:</b> Good<br>")
        layovers = flight.get("layovers")
        if not layovers or (isinstance(layovers, int) and layovers == 0):
            output.append("✅ <b>Direct Flight</b><br>")
        elif isinstance(layovers, list) and layovers:
            output.append(f"🔄 <b>{len(layovers)} Stop(s):</b><br>")
            for stop in layovers:
                output.append(f" - {stop.get('city', 'Unknown City')} ({stop.get('airport_code', '')}): {stop.get('airport_name', '')}, {stop.get('duration_label', '')}<br>")
        elif isinstance(layovers, int):
            output.append(f"🔄 <b>{layovers} Stop(s)</b><br>")
        else:
            output.append("🔄 <b>Layover information unavailable</b><br>")
        output.append("<hr>")
    return "".join(output)

def get_flight_info(user_input):
    """
    Enhanced flight search with better error handling and debugging
    """
    print(f"🔍 DEBUG: Processing input: '{user_input}'")
    
    # Preprocess relative dates
    processed_input = preprocess_relative_dates(user_input)
    print(f"🔍 DEBUG: After date preprocessing: '{processed_input}'")

    origin_city, destination_city, date_str = extract_flight_details(processed_input)
    print(f"🔍 DEBUG: Extracted - Origin: '{origin_city}', Destination: '{destination_city}', Date: '{date_str}'")

    if not origin_city or not destination_city:
        return f"❌ <b>Could not extract city names from:</b> '{user_input}'<br>Detected: Origin='{origin_city}', Destination='{destination_city}'<br>"

    departure_id = get_iata_code(origin_city)
    arrival_id = get_iata_code(destination_city)
    print(f"🔍 DEBUG: IATA codes - Origin: '{departure_id}', Destination: '{arrival_id}'")

    if not departure_id or not arrival_id:
        return f"❌ <b>Could not resolve IATA codes for:</b> '{origin_city}' → '{departure_id}', '{destination_city}' → '{arrival_id}'<br>"

    outbound_date = format_date(date_str or "")
    print(f"🔍 DEBUG: Formatted date: '{outbound_date}' from '{date_str}'")
    
    if not outbound_date:
        return f"❌ <b>Invalid or missing date:</b> '{date_str}'<br>Please use formats like: '30 August', 'tomorrow', '2025-08-30'<br>"

    querystring = {
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "travel_class": "ECONOMY",
        "adults": "1",
        "show_hidden": "1",
        "currency": "INR",
        "language_code": "en-US",
        "country_code": "US"
    }

    try:
        url = f"https://{RAPIDAPI_HOST}/api/v1/searchFlights"
        print(f"🔍 DEBUG: Making API call with params: {querystring}")
        response = requests.get(url, headers=HEADERS, params=querystring)
        response.raise_for_status()
        data = response.json()
        return print_flight_results(data)
    except Exception as e:
        return f"❌ <b>API flight search failed:</b> {str(e)}<br>"

def preprocess_relative_dates(text):
    """
    Enhanced relative date preprocessing - only process actual date phrases
    """
    # Use dateparser search to find all date phrases
    try:
        result = search_dates(text, settings={'PREFER_DATES_FROM': 'future'})
        if result:
            # Sort by length (longest first) to avoid partial replacements
            result.sort(key=lambda x: len(x[0]), reverse=True)
            for phrase, dt in result:
                # Only replace if the phrase looks like a date (not a city name)
                if is_likely_date_phrase(phrase):
                    iso_date = dt.strftime("%Y-%m-%d")
                    text = text.replace(phrase, iso_date)
    except:
        # If dateparser fails, fall back to manual processing
        pass
    
    return text

def is_likely_date_phrase(phrase):
    """Check if a phrase is likely a date and not a city name"""
    phrase_lower = phrase.lower().strip()
    
    # Known city names that shouldn't be treated as dates
    city_names = ['tokyo', 'mumbai', 'delhi', 'london', 'paris', 'new york', 'bangkok', 'singapore']
    if phrase_lower in city_names:
        return False
    
    # Common date indicators
    date_indicators = [
        'tomorrow', 'today', 'yesterday', 'next', 'this',
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'jan', 'feb', 'mar', 'apr', 'may', 'jun',
        'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
        'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'
    ]
    
    # Check if phrase contains date indicators
    for indicator in date_indicators:
        if indicator in phrase_lower:
            return True
    
    # Check if phrase contains numbers (likely dates)
    if re.search(r'\d', phrase):
        return True
    
    return False

# Test function to help debug
def test_extraction(test_cases):
    """Test function to debug extraction"""
    for case in test_cases:
        print(f"\nTesting: '{case}'")
        origin, dest, date = extract_flight_details(case)
        print(f"Result: Origin='{origin}', Destination='{dest}', Date='{date}'")
        formatted_date = format_date(date)
        print(f"Formatted date: '{formatted_date}'")

"""
# Example usage for testing
if __name__ == "__main__":
    test_cases = [
        "search flights from tokyo to mumbai on 30 august",
        "search flights from tokyo to mumbai for 30 august",
        "search flights from tokyo to mumbai 28 august",
        "from london to paris tomorrow",
        "from new york to delhi 2025-08-30",
        "flights from mumbai to bangkok next friday"
    ]
    test_extraction(test_cases)
"""