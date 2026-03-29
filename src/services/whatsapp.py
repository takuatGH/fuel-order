"""whatsapp cloud api client.

handles outbound messaging to whatsapp users via meta's graph api.

api reference: https://developers.facebook.com/docs/whatsapp/cloud-api

message types supported:
- text: plain text messages
- interactive: buttons and list menus (coming soon)
- template: pre-approved message templates (coming soon)

note on rate limits:
- meta enforces rate limits per phone number
- implement exponential backoff for 429 responses
- consider queueing for high-volume scenarios
"""
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class WhatsAppError(Exception):
    """raised when whatsapp api returns an error."""
    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(f"whatsapp api error {status_code}: {error_data}")


class WhatsAppClient:
    """
    client for whatsapp cloud api.
    
    usage:
        client = WhatsAppClient(
            phone_number_id="123456789",
            access_token="EAAxx..."
        )
        await client.send_text_message(to="+27821234567", text="Hello!")
    """
    
    BASE_URL = "https://graph.facebook.com"
    
    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        api_version: str = "v18.0",
    ):
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.api_version = api_version
        
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )
    
    @property
    def messages_url(self) -> str:
        """url for sending messages."""
        return f"{self.BASE_URL}/{self.api_version}/{self.phone_number_id}/messages"
    
    async def send_text_message(self, to: str, text: str) -> dict:
        """
        send a plain text message.
        
        args:
            to: recipient phone number in international format (e.g., "27821234567")
            text: message text (max 4096 characters)
        
        returns:
            api response with message id
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": text}
        }
        
        return await self._send(payload)
    
    async def send_interactive_buttons(
        self,
        to: str,
        body_text: str,
        buttons: list[dict[str, str]],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> dict:
        """
        send an interactive message with buttons.
        
        args:
            to: recipient phone number
            body_text: main message text
            buttons: list of {"id": "btn_id", "title": "Button Text"} (max 3)
            header_text: optional header
            footer_text: optional footer
        
        returns:
            api response with message id
        """
        # whatsapp allows max 3 buttons
        if len(buttons) > 3:
            raise ValueError("whatsapp allows maximum 3 buttons")
        
        interactive = {
            "type": "button",
            "body": {"text": body_text},
            "action": {
                "buttons": [
                    {"type": "reply", "reply": {"id": btn["id"], "title": btn["title"]}}
                    for btn in buttons
                ]
            }
        }
        
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": interactive
        }
        
        return await self._send(payload)
    
    async def send_location_request(self, to: str, body_text: str) -> dict:
        """
        send a location request message.
        
        this prompts the user to share their location.
        
        args:
            to: recipient phone number
            body_text: message asking for location
        
        returns:
            api response with message id
        """
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "location_request_message",
                "body": {"text": body_text},
                "action": {"name": "send_location"}
            }
        }
        
        return await self._send(payload)
    
    async def _send(self, payload: dict) -> dict:
        """
        send a message to the whatsapp api.
        
        handles common error cases and logging.
        """
        try:
            response = await self._client.post(self.messages_url, json=payload)
            
            if response.status_code == 200:
                data = response.json()
                message_id = data.get("messages", [{}])[0].get("id")
                logger.info(f"message sent successfully: {message_id}")
                return data
            
            # handle errors
            error_data = response.json() if response.content else {}
            logger.error(
                f"whatsapp api error: status={response.status_code}, "
                f"error={error_data}"
            )
            raise WhatsAppError(response.status_code, error_data)
        
        except httpx.RequestError as e:
            logger.error(f"whatsapp api request failed: {e}")
            raise WhatsAppError(0, {"error": str(e)})
    
    async def close(self):
        """close the http client."""
        await self._client.aclose()