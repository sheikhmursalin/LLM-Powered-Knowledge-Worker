# setup_token.py
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os, pickle

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/calendar.events',
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/userinfo.email',
          'openid']

flow = InstalledAppFlow.from_client_secrets_file(
    'credentials/credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

with open('credentials/token.json', 'w') as token:
    token.write(creds.to_json())

print("\nToken saved to credentials/token.json")
