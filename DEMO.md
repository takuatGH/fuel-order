# FuelFlow Phone Demo Guide

## Quick Start

1. **Run the startup script:**
   ```powershell
   cd C:\Projects\fuel-order
   .\start.ps1
   ```

2. **Start ngrok tunnel (new terminal):**
   ```powershell
   ngrok http 8000
   ```

3. **Copy the ngrok HTTPS URL** (looks like `https://xxxx.ngrok-free.app`)

---

## WhatsApp Business Setup

### Configure Webhook in Meta Developer Console

1. Go to: https://developers.facebook.com/apps
2. Select your app → WhatsApp → Configuration
3. Click **Edit** on Webhook
4. Enter:
   - **Callback URL**: `https://YOUR-NGROK-URL/webhook`
   - **Verify Token**: (from your `.env` file, `WHATSAPP_VERIFY_TOKEN`)
5. Click **Verify and Save**
6. Subscribe to: `messages`

### Update .env File
Make sure these are set:
```env
WHATSAPP_ACCESS_TOKEN=your_token_here
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_VERIFY_TOKEN=your_verify_token
WHATSAPP_WEBHOOK_SECRET=your_app_secret
```

---

## Demo Script (What to Say on Phone)

| You Say | Bot Responds |
|---------|--------------|
| "Hi" or "Order" | Welcome message, asks for fuel type |
| "Diesel" | Asks for quantity |
| "500" | Asks for location |
| *(Share location)* | Shows order summary, asks to confirm |
| "Yes" | ✅ Order placed! Shows order number |

---

## Troubleshooting

- **Webhook not receiving**: Check ngrok is running, URL is correct
- **Bot not responding**: Check uvicorn terminal for errors
- **Database error**: Run `docker ps` to verify containers are healthy

---

## Stop Everything

```powershell
# Stop server: Ctrl+C in uvicorn terminal
# Stop ngrok: Ctrl+C in ngrok terminal
# Stop containers:
docker compose -f docker/docker-compose.yml down
```
