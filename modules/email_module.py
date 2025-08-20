# modules/email_module.py
import os
import json
import base64
import traceback
import re
import mimetypes
import math
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email import encoders
import openai
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client for Groq
client = openai.OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

# Global variable to store draft email
current_draft = None
current_email_details = None  # For storing email details when replying
temp_attachments_file = None  # For storing temporary attachment file path

# Ensure global variables are properly initialized
if 'current_draft' not in globals():
    current_draft = None
if 'current_email_details' not in globals():
    current_email_details = None
if 'temp_attachments_file' not in globals():
    temp_attachments_file = None

def get_label_mapping():
    """Map user-friendly category names to Gmail labels"""
    return {
        "INBOX": "INBOX",
        "CATEGORY_PERSONAL": "CATEGORY_PERSONAL", 
        "CATEGORY_SOCIAL": "CATEGORY_SOCIAL",
        "CATEGORY_PROMOTIONS": "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES": "CATEGORY_UPDATES",
        "CATEGORY_FORUMS": "CATEGORY_FORUMS",
        "SENT": "SENT",
        "SPAM": "SPAM", 
        "TRASH": "TRASH",
        "DRAFT": "DRAFT"
    }

def get_category_display_name(label):
    """Get user-friendly display name for Gmail labels"""
    display_names = {
        "INBOX": "Primary Inbox",
        "CATEGORY_PERSONAL": "Personal",
        "CATEGORY_SOCIAL": "Social", 
        "CATEGORY_PROMOTIONS": "Promotions",
        "CATEGORY_UPDATES": "Updates",
        "CATEGORY_FORUMS": "Forums",
        "SENT": "Sent",
        "SPAM": "Spam",
        "TRASH": "Trash", 
        "DRAFT": "Drafts"
    }
    return display_names.get(label, label)

def detect_hinglish_context(text):
    """Detect if user wants Hinglish based on context"""
    hinglish_indicators = [
        'kal', 'aaj', 'mat', 'nahi', 'hai', 'hoon', 'ho', 'aana', 'jana', 
        'kya', 'kaise', 'kyun', 'ji', 'sahab', 'maam', 'bhai', 'didi',
        'chutti', 'holiday', 'college', 'office', 'ghar', 'padhna'
    ]
    
    text_lower = text.lower()
    hinglish_count = sum(1 for word in hinglish_indicators if word in text_lower)
    
    return hinglish_count >= 2 or any(word in text_lower for word in ['ji', 'sahab', 'maam'])

def generate_smart_email_content(to_email, subject, context="", previous_content="", is_edit=False, is_reply=False, original_email=None):
    """Generate email content using AI with proper context understanding"""
    try:
        # Detect language preference
        full_context = f"{subject} {context}".lower()
        use_hinglish = detect_hinglish_context(full_context)
        
        # Create appropriate system prompt
        if use_hinglish:
            system_prompt = """You are an AI assistant that writes emails in natural Hinglish (Hindi-English mix). 
            Write professional but friendly emails mixing Hindi and English naturally.
            Use words like: aap, ji, maam, sir, kal (tomorrow), aaj (today), mat (don't), nahi (no), hai, hoon, chutti (leave), etc.
            
            IMPORTANT RULES:
            1. Understand the actual meaning - if someone says "kal mat aana college" it means "don't come to college tomorrow"
            2. Write contextually appropriate content based on what the user actually wants to communicate
            3. Keep it professional but natural
            4. Always end with "Best regards" or "Dhanyawad" followed by RMM
            5. NEVER include phrases like "Here is the updated content" or "Updated email content"
            6. Return ONLY the email body content, nothing else"""
        else:
            system_prompt = """You are an AI assistant that writes professional emails in English.
            
            IMPORTANT RULES:
            1. Understand the actual context and meaning of what user wants to communicate
            2. Write appropriate professional content based on the real intent
            3. Keep tone professional but friendly
            4. Always end with "Best regards" followed by RMM
            5. NEVER include phrases like "Here is the updated content" or "Updated email content"  
            6. Return ONLY the email body content, nothing else"""
        
        # Create context-aware prompts
        if is_edit and previous_content:
            # This is an edit request
            user_prompt = f"""Edit this email based on the instruction: "{context}"

Current email content:
{previous_content}

Provide ONLY the updated email body content (no extra text or explanations)."""
            
        elif is_reply and original_email:
            # This is a reply
            user_prompt = f"""Write a reply to this email:

From: {original_email.get('sender', 'Unknown')}
Subject: {original_email.get('subject', 'No Subject')}
Original Message: {original_email.get('body', original_email.get('snippet', ''))}

Reply context: {context}

Provide ONLY the reply email body content."""
            
        else:
            # This is a new email - provide context clues
            context_explanation = ""
            subject_lower = subject.lower()
            context_lower = context.lower()
            
            # Add context clues for better understanding
            if "kal mat aana" in context_lower or "don't come tomorrow" in context_lower:
                context_explanation = "This is about informing someone not to come tomorrow (holiday/leave notification)"
            elif "chutti" in context_lower or "leave" in context_lower:
                context_explanation = "This is about taking leave or holiday"
            elif "meeting" in context_lower:
                context_explanation = "This is about scheduling or discussing a meeting"
            elif "holiday" in subject_lower or "chutti" in subject_lower:
                context_explanation = "This is about a holiday or leave notification"
            
            user_prompt = f"""Write a professional email with:
Subject: {subject}
Context: {context}
{context_explanation}

Provide ONLY the email body content (no headers, no extra explanations)."""
        
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean up any unwanted prefixes
        unwanted_prefixes = [
            "here is the updated email content:",
            "here's the updated email content:",
            "updated email content:",
            "here is the email:",
            "here's the email:",
            "email content:",
            "dear"
        ]
        
        content_lower = content.lower()
        for prefix in unwanted_prefixes:
            if content_lower.startswith(prefix):
                content = content[len(prefix):].strip()
                break
        
        # Ensure proper signature if missing
        if "best regards" not in content.lower() and "dhanyawad" not in content.lower():
            if use_hinglish:
                content += "\n\nDhanyawad,\nRMM"
            else:
                content += "\n\nBest regards,\nRMM"
        elif "[your name]" in content.lower() or "RMM" not in content.lower():
            content = re.sub(r'\[your name\]', 'RMM', content, flags=re.IGNORECASE)
        
        return content
        
    except Exception as e:
        # Fallback based on context
        if "kal mat aana" in context.lower() or "holiday" in subject.lower():
            return f"""Dear Mahvish Ma'am,

I hope aap well ho. Kal college mat aana - holiday hai.

Dhanyawad,
RMM"""
        else:
            return f"""Dear Sir/Madam,

I hope this email finds you well.

I wanted to reach out regarding {subject.lower()}.

Please let me know your thoughts.

Best regards,
RMM"""

def get_email_body(msg_data):
    """Extract and concatenate all plain text parts from Gmail message data, fallback to stripped HTML if needed."""
    def extract_all_plain_text(payload):
        texts = []
        if payload.get('mimeType', '').startswith('multipart/'):
            parts = payload.get('parts', [])
            for part in parts:
                texts.extend(extract_all_plain_text(part))
        elif payload.get('mimeType') == 'text/plain':
            data = payload.get('body', {}).get('data', '')
            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    texts.append(decoded)
                except Exception:
                    pass
        return texts

    def extract_first_html(payload):
        if payload.get('mimeType', '').startswith('multipart/'):
            parts = payload.get('parts', [])
            for part in parts:
                html = extract_first_html(part)
                if html:
                    return html
        elif payload.get('mimeType') == 'text/html':
            data = payload.get('body', {}).get('data', '')
            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                    return decoded
                except Exception:
                    pass
        return None

    def strip_html(html):
        # Remove script/style tags and all HTML tags
        html = re.sub(r'(?is)<(script|style).*?>.*?(</\1>)', '', html)
        html = re.sub(r'(?s)<.*?>', '', html)
        html = re.sub(r'\s+', ' ', html)
        return html.strip()

    try:
        payload = msg_data.get('payload', {})
        text_parts = extract_all_plain_text(payload)
        if text_parts:
            return "\n\n---\n\n".join(text_parts)
        # Fallback: try to get HTML and strip tags
        html_content = extract_first_html(payload)
        if html_content:
            return strip_html(html_content)
        # Final fallback: Gmail snippet
        return msg_data.get('snippet', 'No plain text content available')
    except Exception:
        return msg_data.get('snippet', 'No plain text content available')

def read_emails_by_category(count=5, label="INBOX"):
    """Read emails from specific category/label"""
    try:
        token_path = os.path.join("credentials", "token.json")
        with open(token_path, 'r') as token_file:
            token_data = json.load(token_file)

        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret")
        )

        service = build('gmail', 'v1', credentials=creds)
        
        # Map label names
        label_mapping = get_label_mapping()
        gmail_label = label_mapping.get(label, "INBOX")
        
        # Get emails from specific category
        query = ""
        if gmail_label.startswith("CATEGORY_"):
            query = f"category:{gmail_label.split('_')[1].lower()}"
        
        if query:
            response = service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=count
            ).execute()
        else:
            response = service.users().messages().list(
                userId='me', 
                labelIds=[gmail_label], 
                maxResults=count
            ).execute()
        
        messages = response.get('messages', [])

        if not messages:
            category_name = get_category_display_name(label)
            return {
                "action": "read_emails",
                "emails": [],
                "category": category_name,
                "total": 0,
                "label": label
            }

        emails = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
            headers = msg_data.get('payload', {}).get('headers', [])
            
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
            from_email = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
            date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
            snippet = msg_data.get('snippet', '')
            body = get_email_body(msg_data)
            
            emails.append({
                "id": msg['id'],
                "sender": from_email,
                "subject": subject,
                "snippet": snippet,
                "body": body,
                "date": date
            })
        
        display_name = get_category_display_name(label)
        
        return {
            "action": "read_emails",
            "emails": emails,
            "category": display_name,
            "total": len(emails),
            "label": label
        }

    except Exception as e:
        traceback.print_exc()
        return {"error": f"Error reading emails: {str(e)}"}

def get_email_details(email_id):
    """Get full email details for viewing/replying"""
    try:
        # If email_id is a number, we need to get the actual Gmail message ID
        if email_id and email_id.isdigit():
            # First, get recent emails to find the one at the specified index
            recent_emails_result = read_emails_by_category(count=20, label="INBOX")
            if recent_emails_result.get("action") == "read_emails":
                emails = recent_emails_result.get("emails", [])
                email_index = int(email_id) - 1  # Convert to 0-based index
                
                if 0 <= email_index < len(emails):
                    email_id = emails[email_index]["id"]  # Get the actual Gmail ID
                else:
                    return {"error": f"Email {email_id} not found. You have {len(emails)} emails available."}
            else:
                return {"error": "Could not retrieve emails to find the specified email."}
        
        token_path = os.path.join("credentials", "token.json")
        with open(token_path, 'r') as token_file:
            token_data = json.load(token_file)

        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret")
        )

        service = build('gmail', 'v1', credentials=creds)
        msg_data = service.users().messages().get(userId='me', id=email_id, format='full').execute()
        
        headers = msg_data.get('payload', {}).get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '(No Subject)')
        from_email = next((h['value'] for h in headers if h['name'] == 'From'), '(Unknown Sender)')
        date = next((h['value'] for h in headers if h['name'] == 'Date'), '')
        body = get_email_body(msg_data)
        
        global current_email_details
        current_email_details = {
            "id": email_id,
            "sender": from_email,
            "subject": subject,
            "body": body,
            "date": date
        }
        
        return {
            "action": "email_details",
            "email": {
                "id": email_id,
                "sender": from_email,
                "subject": subject,
                "date": date,
                "body": body  # <-- Make sure this is the full body
            }
        }
        
    except Exception as e:
        traceback.print_exc()
        return {"error": f"Error getting email details: {str(e)}"}

def format_file_size(bytes):
    """Format file size in human readable format"""
    if bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(bytes, 1024)))
    p = math.pow(1024, i)
    s = round(bytes / p, 2)
    return f"{s} {size_names[i]}"

def get_file_icon(filename):
    """Get emoji icon for file type"""
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    icons = {
        'pdf': '📄', 'doc': '📝', 'docx': '📝', 'txt': '📄',
        'xls': '📊', 'xlsx': '📊', 'csv': '📊',
        'ppt': '📈', 'pptx': '📈',
        'jpg': '🖼️', 'jpeg': '🖼️', 'png': '🖼️', 'gif': '🖼️',
        'mp4': '🎥', 'avi': '🎥', 'mov': '🎥',
        'mp3': '🎵', 'wav': '🎵', 'zip': '📦', 'rar': '📦'
    }
    return icons.get(ext, '📎')

def add_attachments_to_email(message, attachments):
    """Attach files to the email message using file paths from Flask session."""
    import os
    from email.mime.base import MIMEBase
    from email import encoders

    for att in attachments:
        filename = att.get('name')
        content_type = att.get('type', 'application/octet-stream')
        file_path = att.get('path')
        if not filename or not file_path or not os.path.exists(file_path):
            print(f"Attachment missing or file not found: {filename} ({file_path})")
            continue

        with open(file_path, 'rb') as f:
            file_data = f.read()

        # Create MIME part
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(file_data)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        message.attach(part)
        print(f"Attached file: {filename} from {file_path}")

def create_email_draft(to, subject, content=None, context="", attachments=[], cc=[], bcc=[]):
    """Create an email draft with AI-generated content and multiple attachments"""
    global current_draft, temp_attachments_file
    
    print(f"🔍 DEBUG: create_email_draft called")
    print(f"🔍 DEBUG: CC: {cc}, BCC: {bcc}")
    print(f"🔍 DEBUG: Attachments received: {len(attachments)}")
    print(f"🔍 DEBUG: temp_attachments_file: {temp_attachments_file}")
    
    if not to:
        return {"action": "chat", "response": "❌ Please specify recipient email address."}
    
    try:
        # FIXED: Proper access to global temp_attachments_file
        if not attachments:
            # Method 1: Check for temp file (most reliable for multiple attachments)
            if temp_attachments_file and os.path.exists(temp_attachments_file):
                try:
                    with open(temp_attachments_file, 'r') as f:
                        temp_attachments = json.load(f)
                        if isinstance(temp_attachments, list):
                            attachments = temp_attachments
                            print(f"🔍 DEBUG: Loaded {len(attachments)} attachments from temp file: {temp_attachments_file}")
                except Exception as e:
                    print(f"🔍 DEBUG: Failed to load from temp file: {e}")
            
            # Method 2: Check Flask session (fallback)
            if not attachments:
                try:
                    from flask import session, has_request_context
                    if has_request_context() and 'current_attachments' in session:
                        session_attachments = session['current_attachments']
                        if isinstance(session_attachments, list):
                            attachments = session_attachments
                        elif session_attachments:
                            attachments = [session_attachments]
                        print(f"🔍 DEBUG: Found {len(attachments)} attachments in Flask session")
                except Exception as e:
                    print(f"🔍 DEBUG: Could not access Flask session: {e}")
        
        print(f"🔍 DEBUG: Final attachment count: {len(attachments)}")
        if attachments:
            print(f"🔍 DEBUG: Attachment filenames: {[att.get('name', 'unknown') for att in attachments]}")
        
        # Generate email content if not provided
        if not content:
            # Include attachment context in email generation
            attachment_context = ""
            if attachments:
                # Use correct field name 'name' from Flask frontend
                file_names = [att.get('name', att.get('filename', 'unknown')) for att in attachments]
                attachment_context = f"\n\nNote: This email includes {len(attachments)} attached file(s): {', '.join(file_names)}"
            
            content = generate_smart_email_content(to, subject, context + attachment_context)
        
        # Create the draft
        current_draft = {
            "to": to,
            "cc": cc if cc else [],
            "bcc": bcc if bcc else [],
            "subject": subject,
            "content": content,
            "attachments": attachments,
            "created_at": datetime.now().isoformat()
        }
        
        print(f"🔍 DEBUG: Draft created successfully with {len(attachments)} attachments")
        
        # Save the state
        import pickle
        try:
            with open('temp_draft.pkl', 'wb') as f:
                pickle.dump(current_draft, f)
            print("🔍 DEBUG: Draft saved to file")
        except Exception as e:
            print(f"🔍 DEBUG: Failed to save draft: {e}")
        
        # Format the response with detailed attachment info
        response = f"📝 Email draft created!<br><br><strong>To:</strong> {to}"
        
        if cc:
            response += f"<br><strong>CC:</strong> {', '.join(cc)}"
        if bcc:
            response += f"<br><strong>BCC:</strong> {', '.join(bcc)}"
        
        if attachments:
            response += f"<br><strong>📎 Attachments ({len(attachments)}):</strong><br>"
            total_size = sum(att.get('size', 0) for att in attachments)
            
            for att in attachments:
                filename = att.get('name', att.get('filename', 'unknown'))
                file_size = format_file_size(att.get('size', 0))
                file_icon = get_file_icon(filename)
                response += f"&nbsp;&nbsp;{file_icon} {filename} ({file_size})<br>"
            
            response += f"<em>Total size: {format_file_size(total_size)}</em><br>"
            
        response += f"""<br><strong>Subject:</strong> {subject}<br><br><strong>Content:</strong><br>{content}<br><br>
✅ Type 'ok' or 'send' to send<br>
❌ Type 'no' or 'cancel' to cancel<br>
✏️ Type 'edit [instruction]' to modify<br>
📧 Type 'add cc/bcc' to add recipients"""
        
        return {
            "action": "email_draft", 
            "message": response
        }
        
    except Exception as e:
        import traceback
        print(f"🔍 DEBUG: Full traceback:")
        traceback.print_exc()
        return {"action": "chat", "response": f"❌ Error creating draft: {str(e)}"}

def create_reply_draft(context=""):
    """Create a reply draft to the current email"""
    global current_email_details, current_draft
    
    if not current_email_details:
        return {"action": "chat", "response": "❌ No email selected to reply to. Please view an email first."}
    
    try:
        # Extract reply information
        original_subject = current_email_details.get('subject', '')
        reply_subject = f"Re: {original_subject}" if not original_subject.startswith('Re:') else original_subject
        to_email = current_email_details.get('sender', '')
        
        # Generate reply content
        content = generate_smart_email_content(
            to_email, 
            reply_subject, 
            context, 
            is_reply=True, 
            original_email=current_email_details
        )
        
        # Create reply draft
        current_draft = {
            "to": to_email,
            "cc": [],
            "bcc": [],
            "subject": reply_subject,
            "content": content,
            "attachments": [],
            "created_at": datetime.now().isoformat(),
            "is_reply": True,
            "original_email_id": current_email_details.get('id')
        }
        
        response = f"""📧 Reply draft created!<br><br>
<strong>To:</strong> {to_email}<br>
<strong>Subject:</strong> {reply_subject}<br><br>
<strong>Content:</strong><br>{content}<br><br>
✅ Type 'ok' or 'send' to send<br>
❌ Type 'no' or 'cancel' to cancel<br>
✏️ Type 'edit [instruction]' to modify"""
        
        return {"action": "email_draft", "message": response}
        
    except Exception as e:
        return {"action": "chat", "response": f"❌ Error creating reply: {str(e)}"}

def edit_email_draft(instruction):
    """Edit the current email draft"""
    global current_draft
    
    if not current_draft:
        # Try to load from file
        try:
            import pickle
            with open('temp_draft.pkl', 'rb') as f:
                current_draft = pickle.load(f)
                print("🔍 DEBUG: Draft loaded from file for editing")
        except:
            return {"action": "chat", "response": "❌ No email draft to edit. Create a draft first."}
    
    try:
        # Handle CC/BCC additions
        if "add cc" in instruction.lower() or "cc:" in instruction.lower():
            cc_match = re.search(r'(?:add cc|cc:)\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', instruction, re.IGNORECASE)
            if cc_match:
                new_cc = cc_match.group(1)
                if new_cc not in current_draft.get('cc', []):
                    current_draft.setdefault('cc', []).append(new_cc)
                    response = f"✅ Added CC: {new_cc}<br><br>"
                else:
                    response = f"⚠️ {new_cc} is already in CC list<br><br>"
            else:
                return {"action": "chat", "response": "❌ Please provide a valid email address for CC."}
        
        elif "add bcc" in instruction.lower() or "bcc:" in instruction.lower():
            bcc_match = re.search(r'(?:add bcc|bcc:)\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', instruction, re.IGNORECASE)
            if bcc_match:
                new_bcc = bcc_match.group(1)
                if new_bcc not in current_draft.get('bcc', []):
                    current_draft.setdefault('bcc', []).append(new_bcc)
                    response = f"✅ Added BCC: {new_bcc}<br><br>"
                else:
                    response = f"⚠️ {new_bcc} is already in BCC list<br><br>"
            else:
                return {"action": "chat", "response": "❌ Please provide a valid email address for BCC."}
        
        else:
            # Edit content
            current_content = current_draft.get('content', '')
            new_content = generate_smart_email_content(
                current_draft.get('to', ''),
                current_draft.get('subject', ''),
                instruction,
                previous_content=current_content,
                is_edit=True
            )
            current_draft['content'] = new_content
            response = f"✏️ Email content updated!<br><br>"
        
        # Save updated draft
        import pickle
        try:
            with open('temp_draft.pkl', 'wb') as f:
                pickle.dump(current_draft, f)
        except Exception as e:
            print(f"🔍 DEBUG: Failed to save updated draft: {e}")
        
        # Format updated draft display
        response += f"<strong>To:</strong> {current_draft.get('to', '')}"
        
        if current_draft.get('cc'):
            response += f"<br><strong>CC:</strong> {', '.join(current_draft['cc'])}"
        if current_draft.get('bcc'):
            response += f"<br><strong>BCC:</strong> {', '.join(current_draft['bcc'])}"
        
        attachments = current_draft.get('attachments', [])
        if attachments:
            response += f"<br><strong>📎 Attachments ({len(attachments)}):</strong><br>"
            for att in attachments:
                file_size = format_file_size(att['size'])
                file_icon = get_file_icon(att['name'])
                response += f"&nbsp;&nbsp;{file_icon} {att['name']} ({file_size})<br>"
        
        response += f"""<br><strong>Subject:</strong> {current_draft.get('subject', '')}<br><br>
<strong>Content:</strong><br>{current_draft.get('content', '')}<br><br>
✅ Type 'ok' or 'send' to send<br>
❌ Type 'no' or 'cancel' to cancel<br>
✏️ Type 'edit [instruction]' to modify further"""
        
        return {"action": "email_draft", "message": response}
        
    except Exception as e:
        return {"action": "chat", "response": f"❌ Error editing draft: {str(e)}"}

def send_email():
    """Send the current draft email"""
    global current_draft
    
    if not current_draft:
        # Try to load from file
        try:
            import pickle
            with open('temp_draft.pkl', 'rb') as f:
                current_draft = pickle.load(f)
                print("🔍 DEBUG: Draft loaded from file for sending")
        except:
            return {"action": "chat", "response": "❌ No email draft to send. Create a draft first."}
    
    try:
        # Load credentials
        token_path = os.path.join("credentials", "token.json")
        with open(token_path, 'r') as token_file:
            token_data = json.load(token_file)

        creds = Credentials(
            token=token_data["token"],
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret")
        )

        service = build('gmail', 'v1', credentials=creds)
        
        # Create the email message
        message = MIMEMultipart()
        message['to'] = current_draft['to']
        message['subject'] = current_draft['subject']
        
        # Add CC and BCC if present
        cc_list = current_draft.get('cc', [])
        bcc_list = current_draft.get('bcc', [])
        
        if cc_list:
            message['cc'] = ', '.join(cc_list)
            print(f"🔍 DEBUG: Added CC: {message['cc']}")
        if bcc_list:
            message['bcc'] = ', '.join(bcc_list)
            print(f"🔍 DEBUG: Added BCC: {message['bcc']}")
        
        # Add the email body
        body = current_draft['content']
        message.attach(MIMEText(body, 'plain'))
        
        # Add attachments if any
        attachments = current_draft.get('attachments', [])
        if attachments:
            print(f"🔍 DEBUG: Adding {len(attachments)} attachments")
            add_attachments_to_email(message, attachments)
        
        print(f"🔍 DEBUG: Email message created successfully")
        
        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        # Send the email
        result = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        print(f"🔍 DEBUG: Email sent successfully with ID: {result.get('id', 'Unknown')}")
        
        # Store sent email info before clearing draft
        recipient = current_draft['to']
        cc_info = f"<br>📧 CC: {', '.join(cc_list)}" if cc_list else ""
        bcc_info = f"<br>📧 BCC: {', '.join(bcc_list)}" if bcc_list else ""
        attachment_info = f" with {len(attachments)} attachments" if attachments else ""
        
        # Clear the draft after successful send
        current_draft = None

        # Remove temp file
        try:
            if os.path.exists('temp_draft.pkl'):
                os.remove('temp_draft.pkl')
                print("🔍 DEBUG: Temp draft file removed")
            # Remove attachment files
            for att in attachments:
                file_path = att.get('path')
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🔍 DEBUG: Attachment file removed: {file_path}")
        except Exception as e:
            print(f"🔍 DEBUG: Failed to remove temp file or attachments: {e}")
        
        return {
            "action": "email_sent",
            "message": f"✅ Email sent successfully{attachment_info}!<br>📧 To: {recipient}{cc_info}{bcc_info}<br>📧 Message ID: {result.get('id', 'Unknown')}"
        }
        
    except Exception as e:
        traceback.print_exc()
        return {"action": "chat", "response": f"❌ Failed to send email: {str(e)}"}

def cancel_draft():
    """Cancel the current draft"""
    global current_draft
    
    current_draft = None
    
    # Remove temp file
    try:
        import os
        if os.path.exists('temp_draft.pkl'):
            os.remove('temp_draft.pkl')
            print("🔍 DEBUG: Draft cancelled and temp file removed")
    except Exception as e:
        print(f"🔍 DEBUG: Failed to remove temp file: {e}")
    
    return {"action": "chat", "response": "❌ Email draft cancelled."}

def handle_gmail_query(parsed_response):
    """Handle all Gmail operations"""
    action = parsed_response.get("action")
    
    if action == "read_emails":
        count = parsed_response.get("count", 5)
        label = parsed_response.get("label", "INBOX")
        return read_emails_by_category(count, label)
    
    elif action == "email_details":
        email_id = parsed_response.get("email_id")
        return get_email_details(email_id)
    
    elif action == "draft_email":
        to = parsed_response.get("to")
        subject = parsed_response.get("subject")
        content = parsed_response.get("content")
        context = parsed_response.get("context", "")
        attachments = parsed_response.get("attachments", [])
        cc = parsed_response.get("cc", [])
        bcc = parsed_response.get("bcc", [])
        return create_email_draft(to, subject, content, context, attachments, cc, bcc)
    
    elif action == "reply_email":
        context = parsed_response.get("context", "")
        return create_reply_draft(context)
    
    elif action == "email_confirmation":
        response = parsed_response.get("response", "").lower()
        if response in ["yes", "ok", "send", "y"]:
            return send_email()
        elif response in ["no", "cancel", "don't send", "n"]:
            return cancel_draft()
    
    elif action == "edit_email":
        instruction = parsed_response.get("instruction", "")
        return edit_email_draft(instruction)
    
    return {"error": "Unknown Gmail action"}

def set_email_state(draft=None, details=None):
    """Set email state - for use with Flask sessions"""
    global current_draft, current_email_details
    current_draft = draft
    current_email_details = details

def get_email_state():
    """Get current email state"""
    return current_draft, current_email_details

def preserve_draft_state():
    """Debug function to check draft state"""
    global current_draft
    print(f"🔍 PRESERVE: current_draft = {current_draft}")
    return current_draft

def restore_draft_state(draft):
    """Debug function to restore draft state"""
    global current_draft
    current_draft = draft
    print(f"🔍 RESTORE: current_draft = {current_draft}")