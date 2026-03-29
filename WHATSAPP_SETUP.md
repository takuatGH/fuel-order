# WhatsApp Business API Setup Guide

## Step 1: Create Meta Developer Account

1. Go to: https://developers.facebook.com/
2. Click **Get Started** or **Log In** (use your Facebook account)
3. Accept the Developer Terms

---

## Step 2: Create a New App

1. Go to: https://developers.facebook.com/apps/create/
2. Select **Business** as app type → Click **Next**
3. Enter:
   - **App Name**: `FuelFlow` (or any name)
   - **App Contact Email**: Your email
   - **Business Account**: (optional, can skip)
4. Click **Create App**

---

## Step 3: Add WhatsApp Product

1. In your app dashboard, scroll to **Add products to your app**
2. Find **WhatsApp** and click **Set up**
3. You'll see the WhatsApp Getting Started page

---

## Step 4: Get Your Credentials

On the WhatsApp **API Setup** page, you'll see:

### Temporary Access Token
- Copy the **Temporary access token** (valid 24 hours)
- This is your `WHATSAPP_ACCESS_TOKEN`

### Phone Number ID
- Under **Send messages**, find **From phone number ID**
- Copy this number (looks like `123456789012345`)
- This is your `WHATSAPP_PHONE_NUMBER_ID`

### Test Phone Number
- Meta gives you a free test number
- You can send TO any verified number (verify in Step 5)

---

## Step 5: Add Your Phone Number for Testing

1. Under **To** field, click **Manage phone number list**
2. Click **Add phone number**
3. Enter YOUR phone number (the one you'll demo with)
4. Enter the verification code sent to you
5. Now you can receive messages from the bot!

---

## Step 6: Configure Webhook

1. Go to **Configuration** in left sidebar
2. Under **Webhook**, click **Edit**
3. Enter:
   - **Callback URL**: `https://42f3-2c0f-f528-45-4edc-d895-70e7-1801-ce0e.ngrok-free.app/webhook`
   - **Verify token**: `fuelflow-verify-token-2026` (we'll use this)
4. Click **Verify and save**
5. Under **Webhook fields**, click **Manage** → Subscribe to **messages**

---

## Step 7: Get App Secret (for signature verification)

1. Go to **App Settings** → **Basic** (left sidebar)
2. Under **App Secret**, click **Show**
3. Copy it - this is your `WHATSAPP_WEBHOOK_SECRET`

---

## Step 8: Update Your .env File

Create/edit `C:\Projects\fuel-order\.env`:

```env
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fuelflow

# Redis
REDIS_URL=redis://localhost:6379

# WhatsApp (fill these in!)
WHATSAPP_ACCESS_TOKEN=your_access_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id_here
WHATSAPP_VERIFY_TOKEN=fuelflow-verify-token-2026
WHATSAPP_WEBHOOK_SECRET=your_app_secret_here

# Settings
ENABLE_SIGNATURE_VERIFICATION=false
DEBUG=true
```

---

## Step 9: Restart the Server

After updating `.env`:
```powershell
# Press Ctrl+C in the uvicorn terminal, then:
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Step 10: Send a Test Message!

Send "Hi" or "Order" to the WhatsApp test number shown in your Meta console.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Webhook verification fails | Check ngrok is running, URL is correct |
| Message not received | Subscribe to "messages" in webhook fields |
| 401 Unauthorized | Access token may have expired (24 hours) |
| No response from bot | Check uvicorn terminal for errors |
