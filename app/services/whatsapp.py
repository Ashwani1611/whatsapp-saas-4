import httpx
from app.config import settings
from loguru import logger


class WhatsAppService:
    def __init__(self, phone_number_id: str, access_token: str):
        self.phone_number_id = phone_number_id
        self.access_token    = access_token
        self.base_url        = f"{settings.META_BASE_URL}/{settings.META_API_VERSION}"
        self.headers         = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type":  "application/json"
        }

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.base_url}/{endpoint}"
        with httpx.Client(timeout=30) as client:
            response = client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()

    def send_text(self, to: str, text: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "text",
            "text":              {"body": text}
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def send_template(self, to: str, template_id: int, db, components: list = None) -> dict:
        from app.models.template import Template
        template = db.query(Template).filter(Template.id == template_id).first()
        if not template:
            raise ValueError(f"Template {template_id} not found")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "template",
            "template": {
                "name":       template.name,
                "language":   {"code": template.language},
                "components": components or template.components.get("message_components", [])
            }
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def send_image(self, to: str, image_url: str, caption: str = "") -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "image",
            "image":             {"link": image_url, "caption": caption}
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def send_document(self, to: str, doc_url: str, filename: str, caption: str = "") -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "document",
            "document": {
                "link":     doc_url,
                "filename": filename,
                "caption":  caption
            }
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def mark_as_read(self, message_id: str) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "status":            "read",
            "message_id":        message_id
        }
        return self._post(f"{self.phone_number_id}/messages", payload)

    def submit_template(self, name: str, category: str, language: str, components: list) -> dict:
        """Submit template to Meta for approval"""
        from app.config import settings
        url = f"{self.base_url}/{{waba_id}}/message_templates"
        payload = {
            "name":       name,
            "category":   category.upper(),
            "language":   language,
            "components": components
        }
        return self._post(url, payload)

    def get_template_status(self, waba_id: str, template_name: str) -> dict:
        """Check template approval status from Meta"""
        url = f"{self.base_url}/{waba_id}/message_templates"
        with httpx.Client(timeout=30) as client:
            response = client.get(
                url,
                headers = self.headers,
                params  = {"name": template_name}
            )
            response.raise_for_status()
            return response.json()
