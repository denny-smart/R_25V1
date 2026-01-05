import requests

url = "http://localhost:8001/api/v1/bot/status"
headers = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer eyJhbGciOiJFUzI1NiIsImtpZCI6ImRiOWUwMmYxLThhYjYtNDBjMS04MzJjLTUxNGY5NWQwYzZlOSIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJodHRwczovL2lrbG1tbGR1eW5ubmFlanhraGh4LnN1cGFiYXNlLmNvL2F1dGgvdjEiLCJzdWIiOiIzMjY0YzIwOC05MDFiLTRhYzEtYjNkZi1iNjgyNzZjZmNhNGQiLCJhdWQiOiJhdXRoZW50aWNhdGVkIiwiZXhwIjoxNzY3NjUzOTUxLCJpYXQiOjE3Njc2NTAzNTEsImVtYWlsIjoib3duZXJraXJpbWlAZ21haWwuY29tIiwicGhvbmUiOiIiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJnb29nbGUiLCJwcm92aWRlcnMiOlsiZ29vZ2xlIl19LCJ1c2VyX21ldGFkYXRhIjp7ImF2YXRhcl91cmwiOiJodHRwczovL2xoMy5nb29nbGV1c2VyY29udGVudC5jb20vYS9BQ2c4b2NJWGUyMmhjeFlVa0tvMU5xV1oxN3BsUGhXd1AtcnA1VkFJUWpQZ2JsYVhPVzZHenc9czk2LWMiLCJlbWFpbCI6Im93bmVya2lyaW1pQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJmdWxsX25hbWUiOiJEZW5pcyBLaXJpbWkiLCJpc3MiOiJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20iLCJuYW1lIjoiRGVuaXMgS2lyaW1pIiwicGhvbmVfdmVyaWZpZWQiOmZhbHNlLCJwaWN0dXJlIjoiaHR0cHM6Ly9saDMuZ29vZ2xldXNlcmNvbnRlbnQuY29tL2EvQUNnOG9jSVhlMjJoY3hZVWtLbzFOcVdaMTdwbFBoV3dQLXJwNVZBSVFqUGdibGFYT1c2R3p3PXM5Ni1jIiwicHJvdmlkZXJfaWQiOiIxMTMwMzc1MDc5ODg4MjQ3MDM0NTAiLCJzdWIiOiIxMTMwMzc1MDc5ODg4MjQ3MDM0NTAifSwicm9sZSI6ImF1dGhlbnRpY2F0ZWQiLCJhYWwiOiJhYWwxIiwiYW1yIjpbeyJtZXRob2QiOiJvYXV0aCIsInRpbWVzdGFtcCI6MTc2NzY1MDM1MX1dLCJzZXNzaW9uX2lkIjoiMjRhMDYyZmItMjIwZC00OTYxLWJmNDYtNWY5N2I3OWYzMjFhIiwiaXNfYW5vbnltb3VzIjpmYWxzZX0.b0rprNWEw1O5Rv6MJ_ycPk9qKs0NbQ2Q3tWcftU8G0NhcPJe6ak6Y92yYo1_JCVznsIxQW8h12xQqftQlf1Nlw",
    "priority": "u=1, i",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "referrer": "https://r25bot.vercel.app/",
    "mode": "cors"
}

try:
    response = requests.get(url, headers=headers)
    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.text)
except Exception as e:
    print(f"Error: {e}")
