import os
import uuid
import tempfile
import base64
import modules.email_module as email_module
from flask import Flask, render_template, request, jsonify, session
from modules.agent_orchestrator import run_agent
from modules.groq import GroqAgent
from modules.hf_agent import HFAgent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

@app.route('/')
def index():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    if 'history' not in session:
        session['history'] = []
    if 'dark_mode' not in session:
        session['dark_mode'] = True
    if 'email_draft' not in session:
        session['email_draft'] = None
    if 'email_details' not in session:
        session['email_details'] = None
    session['provider'] = 'Groq'  # <-- default provider
    return render_template('index2.html')

@app.route('/toggle_theme', methods=['POST'])
def toggle_theme():
    session['dark_mode'] = not session.get('dark_mode', True)
    return jsonify({'dark_mode': session['dark_mode']})

@app.route('/get_provider_info', methods=['POST'])
def get_provider_info():
    provider = request.json.get('provider', 'HuggingFace')
    try:
        if provider == "HuggingFace":
            agent = HFAgent()
            return jsonify({
                "agent_name": "hf_worker",
                "model": agent.model,
                "display_model": agent.model.split('/')[-1] if '/' in agent.model else agent.model
            })
        elif provider == "Groq":
            agent = GroqAgent()
            return jsonify({
                "agent_name": "groq_worker", 
                "model": agent.model,
                "display_model": agent.model.split('/')[-1] if '/' in agent.model else agent.model
            })
    except Exception as e:
        return jsonify({
            "agent_name": "error",
            "model": f"Error: {str(e)}",
            "display_model": "Error loading model"
        }), 500

@app.route('/send_message', methods=['POST'])
def send_message():
    user_input = request.json.get('message', '').strip()
    provider = request.json.get('provider', 'HuggingFace')
    attachments = request.json.get('attachments', [])

    # Save files to disk and store only metadata + path in session
    attachment_refs = []
    for att in attachments:
        if 'data' in att and 'name' in att:
            file_data = att['data']
            # Remove data URL prefix if present
            if isinstance(file_data, str) and file_data.startswith('data:'):
                file_data = file_data.split(',', 1)[1]
            file_bytes = base64.b64decode(file_data)
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='_' + att['name'])
            temp_file.write(file_bytes)
            temp_file.close()
            attachment_refs.append({
                'name': att['name'],
                'type': att.get('type', 'application/octet-stream'),
                'size': att.get('size', 0),
                'path': temp_file.name
            })
    # Always store as a list
    if attachment_refs:
        session['current_attachments'] = attachment_refs
    else:
        session.pop('current_attachments', None)

    if not user_input and not attachments:
        return jsonify({'error': 'Empty message and no attachments'}), 400

    exit_keywords = [
        "bye", "goodbye", "exit", "quit", "see you", "thank you", "thanks", 
        "thankyou", "see ya", "farewell"
    ]
    if any(kw in user_input.lower() for kw in exit_keywords):
        session['history'] = []
        session['email_draft'] = None
        session['email_details'] = None
        return jsonify({
            'reset': True,
            'message': 'Chat reset. Start a new conversation!'
        })

    if 'history' not in session:
        session['history'] = []

    display_input = user_input
    if attachments:
        file_names = [att['name'] for att in attachments]
        display_input += f" [📎 {len(attachments)} files: {', '.join(file_names)}]"

    session['history'].append(('You', display_input))

    import modules.email_module as email_module
    email_module.current_draft = session.get('email_draft')
    email_module.current_email_details = session.get('email_details')

    # Pass only metadata and path to the agent
    # No need to store base64 data in session

    if provider == "HuggingFace":
        agent_name = "hf_worker"
    else:
        agent_name = "groq_worker"

    try:
        agent_response = run_agent(agent_name, user_input, suppress_output=True)
        session['history'].append(('Agent', agent_response))

        session['email_draft'] = email_module.current_draft
        session['email_details'] = email_module.current_email_details

        # Clean up attachments from session after processing
        # if 'current_attachments' in session:
        #     for att in session['current_attachments']:
        #         if 'path' in att and os.path.exists(att['path']):
        #             try:
        #                 os.remove(att['path'])
        #             except:
        #                 pass
        #     session.pop('current_attachments', None)

        response_data = {
            'response': agent_response,
            'history': session['history']
        }

        if session.get('email_draft'):
            response_data['email_draft'] = session['email_draft']
        elif session.get('email_details'):
            response_data['email_details'] = session['email_details']

        return jsonify(response_data)
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        session['history'].append(('Agent', error_msg))
        return jsonify({
            'response': error_msg,
            'history': session['history']
        })

@app.route('/get_history', methods=['GET'])
def get_history():
    return jsonify({'history': session.get('history', [])})

@app.route('/reset_chat', methods=['POST'])
def reset_chat():
    session['history'] = []
    session['email_draft'] = None
    session['email_details'] = None
    import modules.email_module as email_module
    email_module.current_draft = None
    email_module.current_email_details = None
    return jsonify({'message': 'Chat reset successfully'})

@app.route('/get_email_status', methods=['GET'])
def get_email_status():
    draft = session.get('email_draft')
    details = session.get('email_details')
    status = {
        'has_draft': draft is not None,
        'has_email_selected': details is not None
    }
    if draft:
        status['draft'] = {
            'to': draft.get('to', ''),
            'subject': draft.get('subject', ''),
            'cc': draft.get('cc', []),
            'bcc': draft.get('bcc', [])
        }
    if details:
        status['selected_email'] = {
            'sender': details.get('sender', ''),
            'subject': details.get('subject', ''),
            'id': details.get('id', '')
        }
    return jsonify(status)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)