import os
import re
import sys
import json
import base64
import requests
from dotenv import load_dotenv
from modules.memory_module import store_text_memory, search_similar_memory
from modules.travel_module import get_flight_info
from modules.calendar_module import create_event, list_upcoming_events, delete_event, delete_all_events, list_holidays, list_holidays_next_month

sys.path.append('.')
from modules.email_module import (
    read_emails_by_category, 
    get_email_details, 
    create_email_draft, 
    send_email, 
    edit_email_draft,
    current_draft,
    current_email_details,
    cancel_draft,
    create_reply_draft  
)
from datetime import datetime, timedelta
import dateparser
import pytz
from flask import session  

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"

DEFAULT_TIME_MAP = {
    "morning": "9am",
    "noon": "12pm",
    "afternoon": "3pm",
    "evening": "6pm",
    "night": "9pm",
    "tonight": "9pm",
}

SYNONYMS = {
    "create": ["add", "schedule", "set", "make", "arrange", "book", "organize"],
    "event": ["meeting", "appointment", "reminder", "call", "session", "meetup", "note"],
}

def normalize_action(text):
    for canonical, syns in SYNONYMS.items():
        for syn in syns:
            text = re.sub(rf"\b{syn}\b", canonical, text, flags=re.IGNORECASE)
    return text

def extract_range(text):
    m = re.search(r"between (.+?) and (.+?)(?:\s|$)", text)
    if m:
        start = dateparser.parse(m.group(1))
        end = dateparser.parse(m.group(2))
        if start and end:
            end = end.replace(hour=23, minute=59, second=59, microsecond=999999)
        return start, end
    return None, None

def preprocess_relative_dates(text):
    now = datetime.now()
    replacements = {
        "day after tomorrow": (now + timedelta(days=2)).strftime("%A %d %B %Y"),
        "tomorrow": (now + timedelta(days=1)).strftime("%A %d %B %Y"),
        "today": now.strftime("%A %d %B %Y"),
    }
    for phrase, date_str in replacements.items():
        text = re.sub(rf"\b{phrase}\b", date_str, text, flags=re.IGNORECASE)
    return text

class GroqAgent:
    def __init__(self, agent_name="default", model=GROQ_MODEL):
        self.agent_name = agent_name
        self.model = model

    def run(self, user_input):
        print(f"🔍 DEBUG: GroqAgent.run() called with: '{user_input}'")
        print(f"🔍 DEBUG: current_draft exists: {current_draft is not None}")
        print(f"🔍 DEBUG: _is_email_request result: {self._is_email_request(user_input)}")
        
        # Enhanced email processing with natural language understanding
        if self._is_email_request(user_input):
            print(f"🔍 DEBUG: Routing to email handler")
            return self._handle_email_request(user_input)

        # Email date range filtering - UPDATED TO USE email_module2
        if any(word in user_input.lower() for word in ["email", "inbox", "mail", "mails", "message", "messages"]):
            range_start, range_end = extract_range(user_input.lower())
            if range_start and range_end:
                # Use email_module2 function instead
                email_result = read_emails_by_category(count=50, label="INBOX")  # Get more emails for filtering
                if email_result.get("action") == "read_emails":
                    emails = email_result.get("emails", [])
                    filtered_emails = []
                    for email in emails:
                        try:
                            email_dt = dateparser.parse(email.get('date', ''))
                            if email_dt and range_start <= email_dt <= range_end:
                                filtered_emails.append(email)
                        except Exception:
                            continue
                    if not filtered_emails:
                        return f"❌ No emails found between {range_start.strftime('%Y-%m-%d')} and {range_end.strftime('%Y-%m-%d')}."
                    
                    response = f"📧 <strong>Emails between {range_start.strftime('%b %d, %Y')} and {range_end.strftime('%b %d, %Y')}:</strong><br><br>"
                    for i, email in enumerate(filtered_emails, 1):
                        sender = email.get('sender', 'Unknown')
                        subject = email.get('subject', '(No Subject)')
                        snippet = email.get('snippet', '')
                        date = email.get('date', '')
                        
                        if len(snippet) > 150:
                            snippet = snippet[:150] + "..."
                        
                        response += f"<strong>📨 Email {i}:</strong><br>"
                        response += f"<strong>From:</strong> {sender}<br>"
                        response += f"<strong>Subject:</strong> {subject}<br>"
                        response += f"<strong>Date:</strong> {date}<br>"
                        response += f"<strong>Preview:</strong> {snippet}<br>"
                        response += "─" * 50 + "<br><br>"
                    
                    return response.strip()

        # 🔍 Step 1: Memory recall
        similar_memories = search_similar_memory(user_input)
        memory_context = "\n".join([m.payload["text"] for m in similar_memories])

        # 🛠️ Step 2: Tool trigger based on user input
        if "flight" in user_input.lower():
            info = get_flight_info(user_input)
            if info.startswith("❌ Could not resolve IATA codes"):
                pass
            else:
                return info

        # Calendar logic with improved NLP robustness
        if "calendar" in user_input.lower() or "event" in user_input.lower() or any(word in user_input.lower() for word in ["meeting", "appointment", "reminder", "call", "holiday", "holidays", "festival", "festivals"]):
            try:
                text = normalize_action(user_input.lower())

                # 1. Delete all events
                if any(word in text for word in ["delete all", "remove all", "clear all"]):
                    result = delete_all_events()
                    return f"🗑️ <b>{result['message']}</b><br>✅ Deleted <b>{result['data']['deleted_count']}</b> events successfully!<br>"

                # 2. Delete by ID
                id_match = re.search(r"(?:delete|remove|cancel) (?:event|meeting|appointment|reminder|call)(?: id)?[:\s]*([a-zA-Z0-9_\-]+)", user_input, re.IGNORECASE)
                if id_match:
                    event_id = id_match.group(1).strip()
                    result = delete_event(event_id)
                    return f"🗑️ <b>Event Deletion:</b><br>{result['message']}<br>"

                # 3. List holidays
                if any(word in text for word in ["holiday", "holidays", "festival", "festivals"]):
                    if any(phrase in text for phrase in ["next month", "upcoming month", "following month"]):
                        result = list_holidays_next_month()
                        if result['status'] == 'error':
                            return f"❌ <b>Error:</b> {result['message']}<br>"
                        holidays_text = f"🎉 <b>Holidays for {result['data']['month']}:</b><br>"
                        for region, holidays in result['data']['holidays'].items():
                            holidays_text += f"<b>🌍 {region}:</b><br>"
                            for holiday in holidays:
                                holidays_text += f"🎊 {holiday['title']} - <b>{holiday['date']}</b><br>"
                        return holidays_text.strip()
                    else:
                        result = list_holidays()
                        if result['status'] == 'error':
                            return f"❌ <b>Error:</b> {result['message']}<br>"
                        if not result['data']:
                            return f"🎉 <b>{result['message']}</b><br>"
                        holidays_text = "<b>🎉 Upcoming Holidays This Month:</b><br>"
                        for region, holidays in result['data'].items():
                            holidays_text += f"<b>🌍 {region}:</b><br>"
                            for holiday in holidays:
                                holidays_text += f"🎊 {holiday['title']} - <b>{holiday['date']}</b><br>"
                        return holidays_text.strip()

                # 4. List events
                if any(word in text for word in ["list", "show", "display", "upcoming"]) and not any(word in text for word in ["holiday", "holidays", "festival", "festivals"]):
                    result = list_upcoming_events()
                    if result['status'] == 'error':
                        return f"❌ <b>Error:</b> {result['message']}<br>"
                    if not result['data']:
                        return f"📅 <b>{result['message']}</b><br>"
                    events_text = "<b>📅 Upcoming Events:</b><br>"
                    for i, event in enumerate(result['data'], 1):
                        events_text += f"<b>{i}. 📋 Event:</b> {event['title']}<br>"
                        events_text += f"<b>🕒 Date:</b> {event['date']}<br>"
                        events_text += f"<b>🆔 ID:</b> {event['event_id']}<br>"
                        events_text += "─" * 40 + "<br>"
                    return events_text.strip()

                # 5. Delete by title or time
                del_title_match = re.search(r"(?:delete|remove|cancel) (?:event|meeting|appointment|reminder|call) (?:called|named|about|titled|with title|regarding)\s*['\"]?([^'\"]+)['\"]?", text)
                del_time = dateparser.parse(user_input)
                if del_title_match or del_time:
                    if del_title_match:
                        result = delete_event(del_title_match.group(1))
                        return f"🗑️ <b>Event Deletion:</b><br>{result['message']}<br>"
                    elif del_time:
                        result = delete_event(str(del_time))
                        return f"🗑️ <b>Event Deletion:</b><br>{result['message']}<br>"

                # 6. Create event (add/schedule/set/make)
                if re.search(r"(add|create|schedule|set|make).*(event|meeting|appointment|reminder|call)", text):
                    title_match = re.search(r"(?:called|named|about|titled|with title|regarding)\s*['\"]?([^'\"]+)['\"]?", text)
                    title = title_match.group(1).strip() if title_match else "New Event"
                    attendee_emails = []
                    cleaned_input = user_input
                    invite_phrase_pattern = r"(invite|send invite to|send invitation to|invite to|send to|with|and)\s+"
                    invite_phrase_match = re.search(invite_phrase_pattern, user_input, re.IGNORECASE)
                    if invite_phrase_match:
                        after_invite = user_input[invite_phrase_match.end():]
                        possible_emails = re.split(r"[\s,]+|and\s+", after_invite)
                        attendee_emails = [e.strip() for e in possible_emails if re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", e.strip())]
                        cleaned_input = user_input[:invite_phrase_match.start()]
                        cleaned_input = re.sub(r'\s+', ' ', cleaned_input).strip()

                    # Only preprocess if "today", "tomorrow", or "day after tomorrow" is present
                    if re.search(r"\b(today|tomorrow|day after tomorrow)\b", cleaned_input, re.IGNORECASE):
                        cleaned_input = preprocess_relative_dates(cleaned_input)

                    # Remove the entire action phrase to extract just the date/time
                    cleaned_input = re.sub(r"^(create|add|schedule|set|make)\s+(a\s+)?(event|meeting|appointment|reminder|call)\s+(on|for)\s+", "", cleaned_input, flags=re.IGNORECASE)
                    # If no "on" or "for", remove just the action phrase
                    if cleaned_input == user_input:  # If no change was made above
                        cleaned_input = re.sub(r"^(create|add|schedule|set|make)\s+(a\s+)?(event|meeting|appointment|reminder|call)\s+", "", cleaned_input, flags=re.IGNORECASE)

                    cleaned_input = cleaned_input.strip(" ,.")

                    dt = dateparser.parse(cleaned_input, settings={"PREFER_DATES_FROM": "future"})

                    # --- Add this block for "today" time check ---
                    if "today" in user_input.lower():
                        requested_time_match = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm))", user_input.lower())
                        if requested_time_match:
                            requested_time = requested_time_match.group(1)
                            today = datetime.now()
                            try:
                                event_time = datetime.strptime(requested_time.strip(), "%I%p").time()
                            except ValueError:
                                try:
                                    event_time = datetime.strptime(requested_time.strip(), "%I:%M%p").time()
                                except Exception:
                                    event_time = datetime.strptime("9am", "%I%p").time()
                            dt = today.replace(hour=event_time.hour, minute=event_time.minute, second=0, microsecond=0)
                            # Check if time has passed
                            if dt < today:
                                return "The time has passed. Please choose another time."
                    # --- End block ---

                    if not dt:
                        day_time_pattern = re.compile(
                            r"\b(?:(next|this)\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b(?:\s+at\s+|\s+)?(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)?",
                            re.IGNORECASE
                        )
                        match = day_time_pattern.search(cleaned_input)
                        if match:
                            which = match.group(1) or "this"
                            day_name = match.group(2).lower()
                            time_str = match.group(3) or "9am"
                            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                            target_idx = days.index(day_name)
                            now = datetime.now()
                            today_idx = now.weekday()
                            if which == "this":
                                days_ahead = (target_idx - today_idx) % 7
                                try:
                                    event_time = datetime.strptime(time_str.strip(), "%I%p").time()
                                except ValueError:
                                    try:
                                        event_time = datetime.strptime(time_str.strip(), "%I:%M%p").time()
                                    except Exception:
                                        event_time = datetime.strptime("9am", "%I%p").time()
                                if days_ahead == 0 and now.time() >= event_time:
                                    days_ahead = 7
                            elif which == "next":
                                days_ahead = (target_idx - today_idx + 7) % 7
                                if days_ahead == 0:
                                    days_ahead = 7
                                else:
                                    days_ahead += 7
                            else:
                                days_ahead = (target_idx - today_idx + 7) % 7
                                if days_ahead == 0:
                                    days_ahead = 7
                            event_date = now + timedelta(days=days_ahead)
                            try:
                                event_time = datetime.strptime(time_str.strip(), "%I%p").time()
                            except ValueError:
                                try:
                                    event_time = datetime.strptime(time_str.strip(), "%I:%M%p").time()
                                except Exception:
                                    event_time = datetime.strptime("9am", "%I%p").time()
                            dt = event_date.replace(hour=event_time.hour, minute=event_time.minute, second=0, microsecond=0)

                    if dt:
                        ist = pytz.timezone("Asia/Kolkata")
                        if dt.tzinfo is None:
                            dt_ist = ist.localize(dt)
                        else:
                            dt_ist = dt.astimezone(ist)
                        dt_utc = dt_ist.astimezone(pytz.UTC)
                        start_time = dt_utc.isoformat()
                        result = create_event(title, start_time, attendees=attendee_emails if attendee_emails else None)
                        if result['status'] == 'success':
                            response = ""
                            response += f"✅ {result['message']}<br>"
                            response += f"<b>📋 Event:</b> {result['data']['title']}<br>"
                            response += f"<b>🕒 Date:</b> {result['data']['date']}<br>"
                            response += f"<b>🆔 ID:</b> {result['data']['event_id']}<br>"
                            if result['data'].get('attendees'):
                                response += f"<b>👥 Attendees:</b> {', '.join(result['data']['attendees'])}<br>"
                            response += "🎉 Your event has been added to your calendar!<br>"
                            return response
                        else:
                            return f"❌ Error: {result['message']}<br>"
                    else:
                        return (
                            "❌ Could not recognize the event time.<br>"
                            "💡 Try specifying a full date and time, e.g.:<br>"
                            "• 'next Friday at 2pm'<br>"
                            "• 'tomorrow 4pm IST'<br>"
                            "• 'August 10th at noon'<br>"
                        )
                # Fallback: try to extract title and time anyway
                title_match = re.search(r"(?:called|named|about|titled|with title|regarding)\s*['\"]?([^'\"]+)['\"]?", text)
                title = title_match.group(1).strip() if title_match else "New Event"
                dt = dateparser.parse(user_input, settings={"PREFER_DATES_FROM": "future"})
                if dt:
                    ist = pytz.timezone("Asia/Kolkata")
                    dt_ist = dt.astimezone(ist) if dt.tzinfo else ist.localize(dt)
                    dt_utc = dt_ist.astimezone(pytz.UTC)
                    start_time = dt_utc.isoformat()
                    result = create_event(title, start_time)
                    if result['status'] == 'success':
                        response = ""
                        response += f"✅ {result['message']}<br>"
                        response += f"<b>📋 Event:</b> {result['data']['title']}<br>"
                        response += f"<b>🕒 Date:</b> {result['data']['date']}<br>"
                        response += f"<b>🆔 ID:</b> {result['data']['event_id']}<br>"
                        response += "🎉 Your event has been added to your calendar!<br>"
                        return response
                    else:
                        return f"❌ Error: {result['message']}<br>"
                else:
                    return (
                        "❌ Please specify a recognizable event time.<br>"
                        "💡 Examples:<br>"
                        "• 'tomorrow 4pm IST'<br>"
                        "• 'next Friday at noon'<br>"
                    )
            except Exception as e:
                return f"❌ Failed to process calendar command: {e}<br>"

        # Enhanced email processing with category support - add this before the existing email processing
        if any(word in user_input.lower() for word in ["email", "inbox", "mail", "mails", "message", "messages", "primary", "social", "promotional", "promotion", "personal", "updates", "forums", "spam", "junk", "trash", "drafts"]):
            # Check for category-specific requests first
            category_patterns = [
                "primary", "social", "promotional", "promotion", "personal", 
                "updates", "forums", "spam", "junk", "trash", "drafts", "sent"
            ]
            
            if any(category in user_input.lower() for category in category_patterns):
                try:
                    count = self._extract_count(user_input)
                    category = self._extract_category(user_input)
                    
                    print(f"🔍 DEBUG: Category-specific request - Category: {category}, Count: {count}")
                    
                    # Use email_module2 function
                    email_result = read_emails_by_category(count=count, label=category)
                    
                    if email_result.get("action") != "read_emails":
                        return f"❌ Failed to read {category.lower()} emails."
                    
                    emails = email_result.get("emails", [])
                    category_name = email_result.get("category", category)
                    
                    if not emails:
                        return f"📭 No emails found in {category_name}."
                    
                    # Format the response
                    response = f"📧 <strong>{category_name} Emails ({len(emails)} found):</strong><br>"
                    
                    for i, email in enumerate(emails, 1):
                        sender = email.get('sender', 'Unknown')
                        subject = email.get('subject', '(No Subject)')
                        snippet = email.get('snippet', email.get('body', ''))
                        date = email.get('date', 'Unknown')
                        
                        # Truncate long content
                        if len(snippet) > 150:
                            snippet = snippet[:150] + "..."
                        
                        response += f"<strong>📨 Email {i}:</strong><br>"
                        response += f"<strong>From:</strong> {sender}<br>"
                        response += f"<strong>Subject:</strong> {subject}<br>"
                        response += f"<strong>Date:</strong> {date}<br>"
                        response += f"<strong>Preview:</strong> {snippet}<br>"
                        response += "─" * 50 + "<br>"
                    
                    response += "<em>💡 Click 'Read More' to view full content.</em>"
                    return response.strip()
                    
                except Exception as e:
                    return f"❌ Failed to read {category} emails: {e}<br>"

        # 💬 Step 3: Call LLM with context
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are a helpful assistant named {self.agent_name}. You can use tools like travel search, calendar, and email. "
                    "For emails, you can read, compose, reply, send, and edit emails. Parse user requests and provide structured responses. "
                    "If a tool fails (e.g., city not found), fall back to providing helpful suggestions, airline options, websites, or sample flights."
                )
            },
            {"role": "user", "content": f"Context:\n{memory_context}\n\nQuery: {user_input}"}
        ]

        try:
            res = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"model": self.model, "messages": messages}
            )
            res.raise_for_status()
            reply = res.json()["choices"][0]["message"]["content"]

            # 🧠 Step 4: Store conversation in memory
            store_text_memory(user_input, {"role": "user", "agent": self.agent_name})
            store_text_memory(reply, {"role": "assistant", "agent": self.agent_name})

            return reply

        except Exception as e:
            return f"❌ Groq API Error: {e}<br>"

    def _is_email_request(self, user_input):
        """Check if the request is email-related"""
        email_keywords = [
            # Reading emails
            "read emails", "check emails", "inbox", "show emails", "email list",
            "latest emails", "recent emails", "new emails", "unread emails",
            "personal emails", "social emails", "promotional emails", "sent emails",
            # Category-specific keywords
            "primary emails", "primary inbox", "main emails", "important emails",
            "social media emails", "social notifications", "promotion emails",
            "promotional emails", "promotions", "offers", "deals", "marketing emails",
            "updates emails", "forum emails", "spam emails", "junk emails",
            "trash emails", "deleted emails", "draft emails", "unsent emails",
            # Composing emails  
            "send email", "compose email", "write email", "draft email", "email to",
            "create email", "new email",
            # Replying
            "reply", "reply to", "respond to", "answer email",
            # Email actions
            "email confirmation", "send draft", "cancel email", "edit email"
        ]
        
        user_lower = user_input.lower()

        # Check for email details patterns (e.g., "email 5 details", "show email 2")
        email_detail_patterns = [
            r'(?:email|message)\s+\d+(?:\s+details?)?',  # "email 1" or "email 1 details"
            r'(?:show|display|open|view)\s+(?:email|message)\s+\d+',  # "show email 1"
            r'details?\s+(?:of\s+)?(?:email|message)\s+\d+',  # "details of email 1"
        ]
        for pattern in email_detail_patterns:
            if re.search(pattern, user_lower):
                print(f"🔍 DEBUG: Detected email details pattern in _is_email_request")
                return True

        # Check for email keywords
        if any(keyword in user_lower for keyword in email_keywords):
            return True
        
        # Check for attachment context
        if self._has_attachments_context(user_input):
            return True
        
        # Check if there's a saved draft file
        draft_exists = False
        try:
            import pickle
            import os
            if os.path.exists('temp_draft.pkl'):
                with open('temp_draft.pkl', 'rb') as f:
                    saved_draft = pickle.load(f)
                    draft_exists = saved_draft is not None
                    print(f"🔍 DEBUG: Found saved draft: {draft_exists}")
        except Exception as e:
            print(f"🔍 DEBUG: Error checking saved draft: {e}")
        
        # Check for email context when there's a draft (either in memory or saved)
        if current_draft or draft_exists:
            # Single word responses when draft exists should be treated as email commands
            if user_lower.strip() in ["ok", "send", "yes", "y", "no", "cancel", "n"]:
                print(f"🔍 DEBUG: Detected email confirmation command: {user_lower}")
                return True
            # Edit commands when draft exists
            if user_lower.startswith("edit ") or "change" in user_lower or "modify" in user_lower:
                return True
            # CC/BCC commands
            if any(phrase in user_lower for phrase in ["add cc", "add bcc", "cc:", "bcc:"]):
                return True
            
        # Check for email context clues
        return self._has_email_context(user_input)

    def _has_email_context(self, user_input):
        """Check for email context clues"""
        user_lower = user_input.lower()
        
        # Check for email-related responses when draft exists
        if current_draft and any(word in user_lower for word in ["ok", "send", "yes", "no", "cancel"]):
            return True
            
        # Check for edit instructions when draft exists
        if current_draft and (user_lower.startswith("edit ") or "change" in user_lower or "modify" in user_lower):
            return True
            
        # Check for CC/BCC additions
        if any(phrase in user_lower for phrase in ["add cc", "add bcc", "cc:", "bcc:"]):
            return True
            
        return False

    def _handle_email_request(self, user_input):
        """Handle email requests with natural language processing"""
        try:
            parsed_request = self._parse_email_request(user_input)
            print(f"🔍 DEBUG: Parsed email request: {parsed_request}")
            result = self._execute_email_action(parsed_request)
            return self._format_email_response(result)
        except Exception as e:
            return f"❌ Email Error: {str(e)}"

    def _parse_email_request(self, user_input):
        """Parse natural language email requests into structured format"""
        user_lower = user_input.lower().strip()

        # Check for read emails request
        if user_lower in ["email", "emails", "show my emails", "read my emails", "show emails", "read emails", "my inbox", "read my inbox"]:
            print(f"🔍 DEBUG: Parsing as read emails (primary inbox) for: {user_lower}")
            return {"action": "read_emails", "count": 5, "label": "INBOX"}

        # Check if there's a saved draft file first
        draft_exists = False
        try:
            import pickle
            import os
            if os.path.exists('temp_draft.pkl'):
                with open('temp_draft.pkl', 'rb') as f:
                    saved_draft = pickle.load(f)
                    draft_exists = saved_draft is not None
                    print(f"🔍 DEBUG: Found saved draft in parse: {draft_exists}")
        except Exception as e:
            print(f"🔍 DEBUG: Error checking saved draft in parse: {e}")
        
        # PRIORITY 1: Handle email confirmations when draft exists
        if (current_draft or draft_exists) and user_lower in ["ok", "send", "yes", "y"]:
            print(f"🔍 DEBUG: Parsing as email confirmation - YES")
            return {"action": "email_confirmation", "response": "yes"}
        elif (current_draft or draft_exists) and user_lower in ["no", "cancel", "don't send", "n"]:
            print(f"🔍 DEBUG: Parsing as email confirmation - NO")
            return {"action": "email_confirmation", "response": "no"}
        
        # PRIORITY 2: Handle edit instructions when draft exists
        if (current_draft or draft_exists) and (user_lower.startswith("edit ") or "change" in user_lower or "modify" in user_lower):
            instruction = re.sub(r'^edit\s+', '', user_input, flags=re.IGNORECASE).strip()
            print(f"🔍 DEBUG: Parsing as edit instruction: {instruction}")
            return {"action": "edit_email", "instruction": instruction}
        
        # PRIORITY 3: Handle CC/BCC additions when draft exists
        if (current_draft or draft_exists) and ("add cc" in user_lower or "cc:" in user_lower):
            print(f"🔍 DEBUG: Parsing as CC addition")
            return {"action": "edit_email", "instruction": user_input}
        if (current_draft or draft_exists) and ("add bcc" in user_lower or "bcc:" in user_lower):
            print(f"🔍 DEBUG: Parsing as BCC addition")
            return {"action": "edit_email", "instruction": user_input}

        # Translation patterns (improved)
        translate_patterns = [
            r'(?:translate|show|display)?\s*(?:the\s*)?(?:email|message)?\s*(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s*(?:email|message)?\s*(?:to|in)\s*([a-zA-Z]+)$',
            r'(?:translate|show|display)?\s*(?:the\s*)?(?:email|message)?\s*(?:to|in)\s*([a-zA-Z]+)\s*(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)$',
            r'(?:translate|show|display)?\s*(\d+|first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th)\s*(?:email|message)?\s*(?:to|in)\s*([a-zA-Z]+)$'
        ]
        for pattern in translate_patterns:
            match = re.search(pattern, user_lower)
            if match:
                idx = None
                lang = None
                # idx first, lang second
                if match.lastindex >= 2:
                    idx = match.group(1)
                    lang = match.group(2)
                # lang first, idx second
                elif match.lastindex == 2:
                    lang = match.group(1)
                    idx = match.group(2)
                # Normalize index
                idx_map = {
                    "first": 1, "1st": 1,
                    "second": 2, "2nd": 2,
                    "third": 3, "3rd": 3,
                    "fourth": 4, "4th": 4,
                    "fifth": 5, "5th": 5
                }
                idx = idx_map.get(idx, idx)
                try:
                    idx = int(idx)
                except Exception:
                    idx = 1
                lang = lang.strip().capitalize()
                print(f"🔍 DEBUG: Parsing as translate email: {idx} to {lang}")
                return {"action": "translate_email", "email_index": idx, "target_language": lang}

        # PRIORITY 4: Handle composing new emails
        if any(phrase in user_lower for phrase in ["send email", "compose email", "write email", "email to", "create email"]) or \
           re.search(r'email\s+[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', user_input, re.IGNORECASE):
            print(f"🔍 DEBUG: Parsing as compose request")
            return self._parse_compose_request(user_input)

        # PRIORITY 5: Handle reading emails by category
        if any(phrase in user_lower for phrase in ["read emails", "check emails", "show emails", "inbox", "latest emails"]):
            count = self._extract_count(user_input)
            category = self._extract_category(user_input)
            print(f"🔍 DEBUG: Parsing as read emails: {category}, count: {count}")
            return {"action": "read_emails", "count": count, "label": category}

        # PRIORITY 6: Handle email details - IMPROVED PATTERN
        # Handle patterns like "email 1 details", "show email 2", "details of email 3"
        email_detail_patterns = [
            r'(?:email|message)\s+(\d+)(?:\s+details?)?',  # "email 1" or "email 1 details"
            r'(?:show|display|open|view)\s+(?:email|message)\s+(\d+)',  # "show email 1"
            r'details?\s+(?:of\s+)?(?:email|message)\s+(\d+)',  # "details of email 1"
            r'(?:email|message)\s+(\w+)\s+details?'  # "email abc123 details"
        ]
        
        for pattern in email_detail_patterns:
            match = re.search(pattern, user_lower)
            if match:
                email_id = match.group(1)
                # Make sure it's not an email address
                if not re.search(r'@', email_id):
                    print(f"🔍 DEBUG: Parsing as email details: {email_id}")
                    return {"action": "email_details", "email_id": email_id}
        
        # Handle generic "details" command
        if "details" in user_lower and not any(word in user_lower for word in ["create", "send", "compose"]):
            print(f"🔍 DEBUG: Parsing as email details (no ID)")
            return {"action": "email_details", "email_id": None}

        # PRIORITY 7: Handle replies
        if any(phrase in user_lower for phrase in ["reply", "respond", "answer"]):
            context = re.sub(r'reply\s+', '', user_input, flags=re.IGNORECASE).strip()
            print(f"🔍 DEBUG: Parsing as reply: {context}")
            return {"action": "reply_email", "context": context}

        # Check for "email X details" or "show email X" pattern
        match = re.search(r"(?:email|show email)\s*(\d+)\s*(?:details|content)?", user_input, re.IGNORECASE)
        if match:
            email_index = int(match.group(1))
            print(f"🔍 DEBUG: Detected email details request for index {email_index}")
            return {"action": "show_email_details", "email_index": email_index}

        # DEFAULT: Default to reading emails if no specific action detected
        category = self._extract_category(user_input)
        print(f"🔍 DEBUG: Parsing as default read emails - Category: {category}")
        return {"action": "read_emails", "count": 5, "label": category}

    def _parse_compose_request(self, user_input):
        """Parse email composition requests"""
        # Extract recipient - improved pattern
        to_match = re.search(r'(?:to|email)\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_input, re.IGNORECASE)
        if not to_match:
            # Try alternative pattern for "send email mayur@email.com"
            to_match = re.search(r'email\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_input, re.IGNORECASE)
        
        to_email = to_match.group(1) if to_match else None
        
        # Extract CC emails
        cc_emails = []
        cc_match = re.search(r'cc\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\s*,\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})*)', user_input, re.IGNORECASE)
        if cc_match:
            cc_emails = [email.strip() for email in cc_match.group(1).split(',')]

        # Extract BCC emails
        bcc_emails = []
        bcc_match = re.search(r'bcc\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:\s*,\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})*)', user_input, re.IGNORECASE)
        if bcc_match:
            bcc_emails = [email.strip() for email in bcc_match.group(1).split(',')]
    
        # Extract subject
        subject_match = re.search(r'subject\s+["\']?([^"\']+)["\']?', user_input, re.IGNORECASE)
        subject = subject_match.group(1).strip() if subject_match else "Message from AI Assistant"
    
        # Extract content/context
        content_match = re.search(r'(?:message|content|saying|about)\s+["\']?([^"\']+)["\']?', user_input, re.IGNORECASE)
        if content_match:
            context = content_match.group(1).strip()
        else:
            context = f"Please compose an appropriate email for: {user_input}"
    
        # FIX: Always fetch attachments from Flask session if available
        attachments = []
        try:
            from flask import session, has_request_context
            if has_request_context() and 'current_attachments' in session:
                print(f"🔍 DEBUG: session['current_attachments']: {session['current_attachments']}")
                session_attachments = session['current_attachments']
                if isinstance(session_attachments, list):
                    attachments = session_attachments
                elif session_attachments:
                    attachments = [session_attachments]
                else:
                    attachments = []
                print(f"🔍 DEBUG: Loaded {len(attachments)} attachments from Flask session")
            else:
                # Fallback: Try temp file only if session is not available
                import modules.email_module as email_module
                temp_file = getattr(email_module, 'temp_attachments_file', None)
                if temp_file and os.path.exists(temp_file):
                    with open(temp_file, 'r') as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            attachments = loaded
                            print(f"🔍 DEBUG: Loaded {len(attachments)} attachments from temp file")
        except Exception as e:
            print(f"🔍 DEBUG: Error loading attachments: {e}")

        print(f"🔍 DEBUG: Final result - CC: {cc_emails}, BCC: {bcc_emails}, Attachments: {len(attachments)}")

        return {
            "action": "draft_email",
            "to": to_email,
            "subject": subject,
            "context": context,
            "content": None,
            "attachments": attachments,
            "cc": cc_emails,
            "bcc": bcc_emails
        }

    def _extract_count(self, user_input):
        """Extract number of emails to show"""
        count_match = re.search(r'(\d+)', user_input)
        if count_match:
            return min(int(count_match.group(1)), 20)  # Limit to 20
        return 5

    def _extract_category(self, user_input):
        """Extract email category from user input"""
        user_lower = user_input.lower()

        # Primary inbox patterns
        if any(phrase in user_lower for phrase in [
            "primary", "primary emails", "primary inbox", "main emails", "important emails", "read primary email"
        ]):
            return "INBOX"

        # Personal category patterns  
        elif any(phrase in user_lower for phrase in [
            "personal", "personal emails", "category personal", "read personal email"
        ]):
            return "CATEGORY_PERSONAL"

        # Social category patterns
        elif any(phrase in user_lower for phrase in [
            "social", "social emails", "social media", "social notifications", "category social", "read social email"
        ]):
            return "CATEGORY_SOCIAL"

        # Promotional category patterns
        elif any(phrase in user_lower for phrase in [
            "promotion", "promotional", "promotional emails", "promotions", "offers", "deals", "marketing", "category promotions", "read promotion email"
        ]):
            return "CATEGORY_PROMOTIONS"

        # Updates category patterns
        elif any(phrase in user_lower for phrase in [
            "updates", "update emails", "updates emails", "category updates", "read updates email"
        ]):
            return "CATEGORY_UPDATES"

        # Forums category patterns
        elif any(phrase in user_lower for phrase in [
            "forums", "forum emails", "category forums", "read forums email"
        ]):
            return "CATEGORY_FORUMS"

        # Sent emails patterns
        elif any(phrase in user_lower for phrase in [
            "sent", "sent emails", "sent items", "outbox", "read sent email"
        ]):
            return "SENT"

        # Spam/Junk patterns
        elif any(phrase in user_lower for phrase in [
            "spam", "junk", "spam emails", "junk emails", "read spam email"
        ]):
            return "SPAM"

        # Trash patterns
        elif any(phrase in user_lower for phrase in [
            "trash", "deleted", "trash emails", "deleted emails", "read trash email"
        ]):
            return "TRASH"

        # Drafts patterns
        elif any(phrase in user_lower for phrase in [
            "drafts", "draft emails", "unsent emails", "read draft email"
        ]):
            return "DRAFT"

        # Default to inbox
        else:
            return "INBOX"

    def _execute_email_action(self, parsed_request):
        """Execute email actions based on parsed request"""
        action = parsed_request.get("action")
        
        if action == "read_emails":
            count = parsed_request.get("count", 5)
            label = parsed_request.get("label", "INBOX")
            print(f"🔍 DEBUG: Executing email action: read_emails")
            result = read_emails_by_category(count=count, label=label)
            # Store email list in session for later details lookup
            try:
                session["last_email_list"] = result.get("emails", [])
            except:
                pass  # Session might not be available
            return result
            
        elif action == "show_email_details" or action == "email_details":
            email_index = parsed_request.get("email_index")
            email_id = parsed_request.get("email_id")
            
            print(f"🔍 DEBUG: Executing email details - Index: {email_index}, ID: {email_id}")
            
            # If we have an index, use it to get the email ID from the last list
            if email_index:
                try:
                    email_list = session.get("last_email_list", [])
                    if 1 <= email_index <= len(email_list):
                        email_id = email_list[email_index - 1].get("id")
                        print(f"🔍 DEBUG: Found email ID: {email_id}")
                    else:
                        return {"error": f"Email {email_index} not found. Please list emails first."}
                except:
                    return {"error": "Could not access email list. Please list emails first."}
            
            # If we have an email_id (either from index lookup or direct), get details
            if email_id:
                details = get_email_details(email_id)
                return details
            else:
                return {"error": "Please specify an email number (e.g., 'email 1 details')"}
                
        elif action == "draft_email":
            to = parsed_request.get("to")
            subject = parsed_request.get("subject")
            content = parsed_request.get("content")
            context = parsed_request.get("context", "")
            attachments = parsed_request.get("attachments", [])
            cc = parsed_request.get("cc", [])
            bcc = parsed_request.get("bcc", [])
            return create_email_draft(to, subject, content, context, attachments, cc, bcc)
            
        elif action == "reply_email":
            context = parsed_request.get("context", "")
            return create_reply_draft(context)
            
        elif action == "email_confirmation":
            response = parsed_request.get("response", "").lower()
            if response in ["yes", "ok", "send", "y"]:
                return send_email()
            elif response in ["no", "cancel", "don't send", "n"]:
                return cancel_draft()
                
        elif action == "edit_email":
            instruction = parsed_request.get("instruction", "")
            return edit_email_draft(instruction)
        
        elif action == "translate_email":
            email_index = parsed_request.get("email_index")
            target_language = parsed_request.get("target_language")
            # Get last email list from session, or fetch if missing
            email_list = session.get("last_email_list", [])
            if not email_list or len(email_list) < email_index:
                # Fetch latest emails if not in session
                email_result = read_emails_by_category(count=max(20, email_index), label="INBOX")
                email_list = email_result.get("emails", [])
                session["last_email_list"] = email_list
            if 1 <= email_index <= len(email_list):
                email = email_list[email_index - 1]
                original_text = email.get("body", "")
                translated_text = self._translate_text(original_text, target_language)
                sender = email.get("sender", "Unknown")
                subject = email.get("subject", "(No Subject)")
                date = email.get("date", "")
                return {
                    "action": "translated_email",
                    "email": {
                        "sender": sender,
                        "subject": subject,
                        "date": date,
                        "original_body": original_text,
                        "translated_body": translated_text,
                        "target_language": target_language.title()
                    }
                }
            else:
                return {"error": f"Email {email_index} not found. Please list emails first."}
        
        return {"error": "Unknown email action"}

    def _format_email_response(self, result):
        """Format email operation results for display"""
        if isinstance(result, dict):
            if "error" in result:
                return f"❌ {result['error']}"
            
            action = result.get("action")
            
            if action == "read_emails":
                return self._format_email_list(result)
            elif action == "email_details" or action == "show_email_details":
                return self._format_email_details(result)
            elif action == "email_draft":
                return result.get("message", "📝 Email draft created!")
            elif action == "email_sent":
                return result.get("message", "✅ Email sent successfully!")
            elif action == "chat":
                return result.get("response", "")
            elif action == "translated_email":
                return self._format_translated_email(result)
            
        return str(result)

    def _format_email_list(self, result):
        """Format email list for clean HTML display"""
        emails = result.get("emails", [])
        category = result.get("category", "Emails")
        
        if not emails:
            return f"📭 No emails found in {category}."
        
        response = f"📧 <strong>{category} ({len(emails)} emails):</strong><br>"
        
        for i, email in enumerate(emails, 1):
            sender = email.get("sender", "Unknown")
            subject = email.get("subject", "(No Subject)")
            snippet = email.get("snippet", "")
            date = email.get("date", "")
            
            # Truncate long content
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."
            
            response += f"<strong>📨 Email {i}:</strong><br>"
            response += f"<strong>From:</strong> {sender}<br>"
            response += f"<strong>Subject:</strong> {subject}<br>"
            response += f"<strong>Date:</strong> {date}<br>"
            response += f"<strong>Preview:</strong> {snippet}<br>"
            # Add Read More button with email index
            response += f"""<button class='read-more-btn' data-email-index='{i}'>Read More</button><br>"""
            response += "─" * 50 + "<br>"

        response += "<em>💡 Click 'Read More' to view full content.</em>"
        return response

    def _format_email_details(self, details):
        """Format email details for display"""
        if isinstance(details, dict) and "error" in details:
            return f"❌ {details['error']}"
            
        if isinstance(details, dict) and "email" in details:
            email = details["email"]
            sender = email.get("sender", "Unknown")
            subject = email.get("subject", "(No Subject)")
            date = email.get("date", "")
            body = email.get("body", "")

            # Use a scrollable, preformatted container for the body
            return f"""📧 <strong>Email Details:</strong><br>
<strong>From:</strong> {sender}
<strong>Subject:</strong> {subject}
<strong>Date:</strong> {date}<br>
<strong>Content:</strong><br>
<div class="email-content-bubble"><pre>{body}</pre></div>
"""
        return f"❌ Could not load email details"

    def _format_translated_email(self, details):
        email = details.get("email", {})
        sender = email.get("sender", "Unknown")
        subject = email.get("subject", "(No Subject)")
        date = email.get("date", "")
        original_body = email.get("original_body", "")
        translated_body = email.get("translated_body", "")
        target_language = email.get("target_language", "")
        return f"""📧 <strong>Email Translated to {target_language}:</strong><br>
<strong>From:</strong> {sender}<br>
<strong>Subject:</strong> {subject}<br>
<strong>Date:</strong> {date}<br>
<strong>Original Content:</strong><br>
<div class="email-content-bubble"><pre>{original_body}</pre></div>
<strong>Translated Content:</strong><br>
<div class="email-content-bubble"><pre>{translated_body}</pre></div>
"""

    def _has_attachments_context(self, user_input):
        """Check if user mentions attachments"""
        attachment_keywords = [
            "attach", "attachment", "file", "document", "pdf", "image", 
            "photo", "send file", "with attachment", "attached file"
        ]
        
        user_lower = user_input.lower()
        return any(keyword in user_lower for keyword in attachment_keywords)

    def _translate_text(self, text, target_language):
        """Translate text to the target language using Groq/OpenAI API."""
        try:
            # Use Groq/OpenAI translation prompt
            prompt = f"Translate the following email to {target_language}:\n\n{text}"
            messages = [
                {"role": "system", "content": "You are a professional translator."},
                {"role": "user", "content": prompt}
            ]
            res = requests.post(
                GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={"model": self.model, "messages": messages}
            )
            res.raise_for_status()
            reply = res.json()["choices"][0]["message"]["content"]
            return reply.strip()
        except Exception as e:
            return f"❌ Translation error: {e}"