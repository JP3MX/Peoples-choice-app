# Emergent Google Auth — Testing Playbook (saved per integration playbook)

This app integrates Emergent-managed Google sign-in ALONGSIDE the existing JWT
email/password auth. After exchanging the Emergent `session_id` server-side, the
backend upserts the user and issues the app's OWN JWT (Authorization: Bearer,
localStorage `sk_token`) so all existing Bearer routes + billing/entitlement work
unchanged. (We do NOT switch the app to cookie sessions.)

## Flow
1. Login page "Continue with Google" -> `https://auth.emergentagent.com/?redirect=<origin>/`
2. User returns to `<origin>/#session_id=...`
3. AuthContext detects the `#session_id` fragment on load (BEFORE the /me check),
   calls `POST /api/auth/google/session` with header `X-Session-ID: <session_id>`.
4. Backend GETs `https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data`
   with `X-Session-ID`, upserts the user by email (auth_provider="google"),
   returns `{ token, user }`. Frontend stores token in localStorage and cleans the hash.

## Backend testing (issue an app JWT for a seeded Google user)
Because the real session-data exchange needs a live Emergent session_id, to test
protected routes you can seed a Google user and mint an app JWT directly:

```
python3 - <<'PY'
import os, jwt
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
email='google.tester@example.com'
u=db.users.find_one({'email':email})
if not u:
    r=db.users.insert_one({'email':email,'password_hash':None,'name':'Google Tester',
        'role':'mechanic','auth_provider':'google','created_at':datetime.now(timezone.utc).isoformat()})
    uid=str(r.inserted_id)
else:
    uid=str(u['_id'])
tok=jwt.encode({'sub':uid,'email':email,'exp':datetime.now(timezone.utc)+timedelta(days=7),'type':'access'},
    os.environ['JWT_SECRET'], algorithm='HS256')
print('APP_JWT', tok)
PY
```
Then: `curl $API/api/auth/me -H "Authorization: Bearer <APP_JWT>"` -> returns the user.

## Test Identity Tracking
- Google test app user (email): google.tester@example.com (auth_provider=google, role=mechanic)
- No app password stored for Google users (OAuth). They may use forgot-password to set one.
- Existing email/password + reviewer/admin: mechanic@squawkking.io / squawk123 (unchanged).
